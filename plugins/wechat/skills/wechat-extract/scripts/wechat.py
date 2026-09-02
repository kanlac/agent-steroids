#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wechat.py — 微信 macOS 4.x 本地聊天库解密与导出管线（只读、纯本地、零封号风险）

前置：先按 references/setup.md 完成一次性初始化（截口令 + 开 FDA）。
依赖：口令文件 <工作目录>/passphrase.hex（一次性用 lldb 截取）
      系统 libcommonCrypto（AES）+ Homebrew libzstd（解压消息）
工作目录：默认 ~/wechat-extract，可用环境变量 WECHAT_EXTRACT_HOME 覆盖。

用法：
  wechat.py decrypt                 解密所有库 → <工作目录>/plain/（增量：源没变则跳过）
  wechat.py groups [-n 20]          列出最近活跃的群
  wechat.py contacts <关键词>       按名字搜群/人，拿到 id
  wechat.py dump <群名或id> [--days N | --since YYYY-MM-DD] [-o 文件]
                                    导出某群某时间段的可读转录（默认最近 2 天）
"""
import os, sys, glob, sqlite3, ctypes, hashlib, datetime, re, argparse

WORKDIR = os.environ.get('WECHAT_EXTRACT_HOME', os.path.expanduser('~/wechat-extract'))
PLAIN = os.path.join(WORKDIR, 'plain')
CONTAINER = os.path.expanduser(
    '~/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files')

PAGE, RESERVE = 4096, 80   # 微信 4.x：SQLCipher4，AES-256-CBC，reserve=IV16+HMAC-SHA512(64)

# ---------- 底层：AES(CommonCrypto) + zstd ----------
_cc = ctypes.CDLL('/usr/lib/system/libcommonCrypto.dylib')
_cc.CCCrypt.restype = ctypes.c_int
_cc.CCCrypt.argtypes = [ctypes.c_uint32]*3 + [
    ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
    ctypes.c_void_p, ctypes.c_size_t,
    ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

def _aes_cbc_dec(key, iv, data):
    out = ctypes.create_string_buffer(len(data)); moved = ctypes.c_size_t(0)
    if _cc.CCCrypt(1, 0, 0, key, 32, iv, data, len(data), out, len(data),
                   ctypes.byref(moved)) != 0:
        raise RuntimeError('CCCrypt failed')
    return out.raw[:moved.value]

def _load_zstd():
    for p in (['/opt/homebrew/lib/libzstd.1.dylib', '/opt/homebrew/lib/libzstd.dylib',
               '/usr/local/lib/libzstd.1.dylib', '/usr/local/lib/libzstd.dylib']
              + glob.glob('/opt/homebrew/Cellar/zstd/*/lib/libzstd.*.dylib')):
        if os.path.exists(p):
            z = ctypes.CDLL(p)
            z.ZSTD_decompress.restype = ctypes.c_size_t
            z.ZSTD_decompress.argtypes = [ctypes.c_char_p, ctypes.c_size_t,
                                          ctypes.c_char_p, ctypes.c_size_t]
            z.ZSTD_isError.restype = ctypes.c_uint
            z.ZSTD_isError.argtypes = [ctypes.c_size_t]
            return z
    return None
_zstd = _load_zstd()

def _unzstd(b):
    if not _zstd:
        return b'<zstd unavailable>'
    out = ctypes.create_string_buffer(1 << 21)
    r = _zstd.ZSTD_decompress(out, 1 << 21, b, len(b))
    return out.raw[:r] if not _zstd.ZSTD_isError(r) else b''

# ---------- 解密 ----------
def _passphrase():
    p = os.path.join(WORKDIR, 'passphrase.hex')
    if not os.path.exists(p):
        sys.exit('缺少口令文件 %s —— 请先按 references/setup.md 用 lldb 截取一次口令' % p)
    return bytes.fromhex(open(p).read().strip())

def _db_root():
    dirs = glob.glob(os.path.join(CONTAINER, 'wxid_*/db_storage'))
    if not dirs:
        sys.exit('找不到微信数据目录：%s\n（微信未登录，或宿主 App 未开完全磁盘访问，见 setup.md 第4步）'
                 % CONTAINER)
    return dirs[0]

def decrypt_file(src, dst, passphrase):
    data = open(src, 'rb').read()
    if data[:16] == b'SQLite format 3\x00':      # 未加密（少见）
        open(dst, 'wb').write(data); return
    key = hashlib.pbkdf2_hmac('sha512', passphrase, data[:16], 256000, 32)
    with open(dst, 'wb') as o:
        for i in range(len(data)//PAGE):
            p = data[i*PAGE:(i+1)*PAGE]
            off = 16 if i == 0 else 0
            iv = p[PAGE-RESERVE:PAGE-RESERVE+16]
            body = _aes_cbc_dec(key, iv, p[off:PAGE-RESERVE])
            o.write((b'SQLite format 3\x00'+body) if i == 0 else body)
            o.write(b'\x00'*RESERVE)

def cmd_decrypt(_):
    os.makedirs(PLAIN, exist_ok=True)
    root = _db_root(); pw = _passphrase()
    targets = (glob.glob(f'{root}/message/message_*.db') +
               glob.glob(f'{root}/message/biz_message_*.db') +
               [f'{root}/contact/contact.db', f'{root}/session/session.db'])
    for src in targets:
        if not os.path.exists(src) or src.endswith('_fts.db'):
            continue
        dst = os.path.join(PLAIN, os.path.basename(src))
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            print('跳过(已最新)', os.path.basename(src)); continue
        try:
            decrypt_file(src, dst, pw)
            print('解密', os.path.basename(src), f'{os.path.getsize(dst)//1024//1024}MB')
        except Exception as e:
            print('解密失败', os.path.basename(src), '—', e,
                  '（口令可能已失效：用户是否退出重登？见 setup.md）')
    print('完成 →', PLAIN)

# ---------- 名字解析 ----------
def _names():
    """username -> 显示名（备注优先，其次昵称）"""
    cp = os.path.join(PLAIN, 'contact.db')
    if not os.path.exists(cp):
        return {}
    c = sqlite3.connect(cp); nm = {}
    for u, nk, rm in c.execute("SELECT username,nick_name,remark FROM contact"):
        if u:
            nm[u] = (rm or nk or u)
    c.close(); return nm

def cmd_groups(a):
    sp = os.path.join(PLAIN, 'session.db')
    if not os.path.exists(sp):
        sys.exit('请先运行 decrypt')
    nm = _names(); s = sqlite3.connect(sp)
    rows = s.execute("SELECT username,last_timestamp,summary FROM SessionTable "
                     "WHERE username LIKE '%@chatroom' ORDER BY last_timestamp DESC "
                     "LIMIT ?", (a.n,)).fetchall()
    for i, (u, ts, summ) in enumerate(rows, 1):
        t = datetime.datetime.fromtimestamp(ts).strftime('%m-%d %H:%M')
        print(f'{i:>2}. {nm.get(u,u)}')
        print(f'     {t}  {u}')
    s.close()

def cmd_contacts(a):
    cp = os.path.join(PLAIN, 'contact.db')
    if not os.path.exists(cp):
        sys.exit('请先运行 decrypt')
    c = sqlite3.connect(cp); kw = a.keyword
    for u, nk, rm in c.execute("SELECT username,nick_name,remark FROM contact"):
        disp = (rm or nk or '')
        if kw in (disp or '') or kw in (u or ''):
            tag = '群' if (u or '').endswith('@chatroom') else '人'
            print(f'[{tag}] {disp}   id={u}')
    c.close()

# ---------- 消息渲染 ----------
def _strip_sender(s):
    i = s.find('\n')
    return s[i+1:] if 0 < i < 70 and s[:i].endswith(':') else s

def _readable(t, mc):
    if mc is None:
        return '[空]'
    if isinstance(mc, bytes):
        mc = _unzstd(mc) if mc[:4] == b'\x28\xb5\x2f\xfd' else mc
        try: mc = mc.decode('utf-8', 'replace')
        except: return '[二进制]'
    body = _strip_sender(mc)
    if t == 1:  return body.strip()
    if t == 47: return '[表情]'
    if t == 3:  return '[图片]'
    if t == 34: return '[语音]'
    if t == 43: return '[视频]'
    if t == 42: return '[名片]'
    if t == 48: return '[位置]'
    if t == 10000: return '[系统] ' + re.sub('<[^>]+>', '', body)[:120]
    m = re.search(r'<title>(.*?)</title>', body, re.S)
    if m:
        title = m.group(1).strip()
        d = re.search(r'<des>(.*?)</des>', body, re.S)
        des = d.group(1).strip() if d else ''
        pre = '[引用回复]' if '<refermsg>' in body else '[分享/链接]'
        return f'{pre} {title}' + (f' — {des[:60]}' if des else '')
    return f'[类型{t}]'

def _find_room(query):
    """按名字或 id 定位群，返回 (chatroom_id, 显示名)"""
    if query.endswith('@chatroom'):
        return query, _names().get(query, query)
    cp = os.path.join(PLAIN, 'contact.db'); c = sqlite3.connect(cp)
    hits = []
    for u, nk, rm in c.execute("SELECT username,nick_name,remark FROM contact "
                               "WHERE username LIKE '%@chatroom'"):
        disp = rm or nk or ''
        if query in disp:
            hits.append((u, disp))
    c.close()
    if not hits:
        sys.exit(f'没找到含“{query}”的群')
    if len(hits) > 1:
        print('匹配到多个群，请用更精确的名字或 id：')
        for u, d in hits[:15]:
            print(f'  {d}   id={u}')
        sys.exit(0)
    return hits[0]

def cmd_dump(a):
    room, disp = _find_room(a.group)
    tab = 'Msg_' + hashlib.md5(room.encode()).hexdigest()
    if a.since:
        cutoff = int(datetime.datetime.strptime(a.since, '%Y-%m-%d').timestamp())
    else:
        cutoff = int((datetime.datetime.now() - datetime.timedelta(days=a.days)).timestamp())
    lines, total = [], 0
    for shard in sorted(glob.glob(os.path.join(PLAIN, 'message_*.db')) +
                        glob.glob(os.path.join(PLAIN, 'biz_message_*.db'))):
        c = sqlite3.connect(shard)
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                         (tab,)).fetchone():
            c.close(); continue
        id2u = {r[0]: r[1] for r in c.execute('SELECT rowid,user_name FROM Name2Id')}
        nm = _names()
        for ct, lt, sid, mc in c.execute(
                f'SELECT create_time,local_type,real_sender_id,message_content '
                f'FROM "{tab}" WHERE create_time>=? ORDER BY create_time', (cutoff,)):
            t = datetime.datetime.fromtimestamp(ct).strftime('%m-%d %H:%M')
            who = nm.get(id2u.get(sid, ''), id2u.get(sid, f'id{sid}'))
            lines.append(f'[{t}] {who}: {_readable(lt, mc)}')
            total += 1
        c.close()
    rng = a.since or f'最近{a.days}天'
    header = f'# {disp}\n# {room} | {rng} | {total} 条\n'
    text = header + '\n'.join(lines)
    if a.out:
        open(a.out, 'w').write(text); print(f'导出 {total} 条 → {a.out}')
    else:
        print(text)

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description='微信 macOS 本地库解密与导出')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('decrypt').set_defaults(func=cmd_decrypt)
    g = sub.add_parser('groups'); g.add_argument('-n', type=int, default=20); g.set_defaults(func=cmd_groups)
    ct = sub.add_parser('contacts'); ct.add_argument('keyword'); ct.set_defaults(func=cmd_contacts)
    d = sub.add_parser('dump')
    d.add_argument('group'); d.add_argument('--days', type=int, default=2)
    d.add_argument('--since'); d.add_argument('-o', '--out')
    d.set_defaults(func=cmd_dump)
    a = ap.parse_args(); a.func(a)

if __name__ == '__main__':
    main()
