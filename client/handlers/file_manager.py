# -*- coding: utf-8 -*-
"""文件管理处理器：接收服务端文件管理指令，执行目录浏览和文件操作。"""

import asyncio
import os
import sys
import stat
import shutil
import platform
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.protocol import MsgType, make_msg

logger = logging.getLogger('client.file_manager')

_IS_WINDOWS = platform.system() == 'Windows'


def _get_permissions(st):
    """根据平台获取权限/属性信息。"""
    if _IS_WINDOWS:
        attrs = []
        try:
            fa = st.st_file_attributes
            if fa & 0x01:   # FILE_ATTRIBUTE_READONLY
                attrs.append('readonly')
            if fa & 0x02:   # FILE_ATTRIBUTE_HIDDEN
                attrs.append('hidden')
            if fa & 0x04:   # FILE_ATTRIBUTE_SYSTEM
                attrs.append('system')
        except AttributeError:
            pass
        return attrs
    else:
        return oct(stat.S_IMODE(st.st_mode))


def _make_entry(name, path, st, detailed=False):
    """构造目录条目字典。"""
    is_dir = stat.S_ISDIR(st.st_mode)
    entry = {
        'name': name,
        'path': path,
        'is_dir': is_dir,
        'size': st.st_size if not is_dir else 0,
        'mtime': datetime.fromtimestamp(st.st_mtime).isoformat(),
        'permissions': _get_permissions(st),
    }
    if detailed:
        entry['atime'] = datetime.fromtimestamp(st.st_atime).isoformat()
        entry['ctime'] = datetime.fromtimestamp(st.st_ctime).isoformat()
        if _IS_WINDOWS:
            try:
                fa = st.st_file_attributes
                entry['attributes'] = {
                    'readonly': bool(fa & 0x01),
                    'hidden': bool(fa & 0x02),
                    'system': bool(fa & 0x04),
                }
            except AttributeError:
                entry['attributes'] = {}
        else:
            entry['mode'] = oct(stat.S_IMODE(st.st_mode))
            entry['uid'] = st.st_uid
            entry['gid'] = st.st_gid
    return entry


# ---------------------------------------------------------------------------
# Sub-handlers
# ---------------------------------------------------------------------------

async def _handle_list(engine, payload, seq):
    """列出目录内容。"""
    path = payload.get('path', '')
    loop = asyncio.get_event_loop()

    # 空路径则返回根目录列表
    if not path:
        await _handle_roots(engine, payload, seq)
        return

    def _list():
        if not os.path.exists(path):
            return None, 'PATH_NOT_FOUND', f'Path not found: {path}'
        if not os.path.isdir(path):
            return None, 'PATH_NOT_FOUND', f'Not a directory: {path}'

        entries = []
        try:
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        st = entry.stat()
                        entries.append(_make_entry(entry.name, entry.path, st))
                    except (OSError, PermissionError):
                        # 跳过无权限访问的条目
                        continue
        except PermissionError:
            return None, 'PERMISSION_DENIED', f'Permission denied: {path}'

        return entries, None, None

    entries, err_code, err_msg = await loop.run_in_executor(None, _list)

    if err_code:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': err_msg, 'code': err_code}, seq)
    else:
        resp = make_msg(MsgType.FILE_MANAGER, engine.client_id,
                        {'action': 'list', 'path': path, 'entries': entries}, seq)
    await engine.send_msg(resp)


async def _handle_roots(engine, payload, seq):
    """获取根目录列表。"""
    loop = asyncio.get_event_loop()

    def _roots():
        if _IS_WINDOWS:
            import ctypes
            roots = []
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if bitmask & (1 << i):
                    letter = chr(ord('A') + i)
                    roots.append(f'{letter}:\\')
            return roots
        else:
            return ['/']

    roots = await loop.run_in_executor(None, _roots)
    resp = make_msg(MsgType.FILE_MANAGER, engine.client_id,
                    {'action': 'roots', 'roots': roots}, seq)
    await engine.send_msg(resp)


async def _handle_search(engine, payload, seq):
    """在目录中递归搜索文件。"""
    path = payload.get('path', '')
    keyword = payload.get('keyword', '')
    max_depth = payload.get('max_depth', 5)
    max_results = payload.get('max_results', 500)
    loop = asyncio.get_event_loop()

    def _search():
        if not os.path.exists(path):
            return None, 'PATH_NOT_FOUND', f'Path not found: {path}'

        keyword_lower = keyword.lower()
        results = []

        for dirpath, dirnames, filenames in os.walk(path):
            # 计算当前深度
            depth = dirpath[len(path):].count(os.sep)
            if depth >= max_depth:
                dirnames.clear()  # 不再深入
                continue

            # 搜索目录名
            for dirname in dirnames:
                if keyword_lower in dirname.lower():
                    full_path = os.path.join(dirpath, dirname)
                    try:
                        st = os.stat(full_path)
                        results.append({
                            'name': dirname,
                            'path': full_path,
                            'is_dir': True,
                            'size': 0,
                            'mtime': datetime.fromtimestamp(st.st_mtime).isoformat(),
                        })
                    except (OSError, PermissionError):
                        pass
                    if len(results) >= max_results:
                        return results, None, None

            # 搜索文件名
            for filename in filenames:
                if keyword_lower in filename.lower():
                    full_path = os.path.join(dirpath, filename)
                    try:
                        st = os.stat(full_path)
                        results.append({
                            'name': filename,
                            'path': full_path,
                            'is_dir': False,
                            'size': st.st_size,
                            'mtime': datetime.fromtimestamp(st.st_mtime).isoformat(),
                        })
                    except (OSError, PermissionError):
                        pass
                    if len(results) >= max_results:
                        return results, None, None

        return results, None, None

    results, err_code, err_msg = await loop.run_in_executor(None, _search)

    if err_code:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': err_msg, 'code': err_code}, seq)
    else:
        resp = make_msg(MsgType.FILE_MANAGER, engine.client_id,
                        {'action': 'search', 'path': path, 'keyword': keyword,
                         'results': results, 'count': len(results)}, seq)
    await engine.send_msg(resp)


async def _handle_rename(engine, payload, seq):
    """重命名文件或目录。"""
    path = payload.get('path', '')
    new_name = payload.get('new_name', '')
    loop = asyncio.get_event_loop()

    def _rename():
        if not os.path.exists(path):
            return None, 'PATH_NOT_FOUND', f'Path not found: {path}'

        new_path = os.path.join(os.path.dirname(path), new_name)
        if os.path.exists(new_path):
            return None, 'ALREADY_EXISTS', f'Target already exists: {new_path}'

        os.rename(path, new_path)
        return {'new_path': new_path}, None, None

    result, err_code, err_msg = await loop.run_in_executor(None, _rename)

    if err_code:
        if err_code == 'PERMISSION_DENIED' or (err_msg and 'Permission' in err_msg):
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': err_msg, 'code': 'PERMISSION_DENIED'}, seq)
        else:
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': err_msg, 'code': err_code}, seq)
    else:
        resp = make_msg(MsgType.FILE_MANAGER, engine.client_id,
                        {'action': 'rename', 'success': True,
                         'old_path': path, 'new_path': result['new_path']}, seq)
    await engine.send_msg(resp)


async def _handle_delete(engine, payload, seq):
    """删除文件或目录。"""
    path = payload.get('path', '')
    loop = asyncio.get_event_loop()

    def _delete():
        if not os.path.exists(path):
            return None, 'PATH_NOT_FOUND', f'Path not found: {path}'

        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return True, None, None

    result, err_code, err_msg = await loop.run_in_executor(None, _delete)

    if err_code:
        if 'Permission' in (err_msg or ''):
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': err_msg, 'code': 'PERMISSION_DENIED'}, seq)
        else:
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': err_msg, 'code': err_code}, seq)
    else:
        resp = make_msg(MsgType.FILE_MANAGER, engine.client_id,
                        {'action': 'delete', 'success': True, 'path': path}, seq)
    await engine.send_msg(resp)


async def _handle_move(engine, payload, seq):
    """移动文件或目录。"""
    source = payload.get('source', '')
    destination = payload.get('destination', '')
    loop = asyncio.get_event_loop()

    def _move():
        if not os.path.exists(source):
            return None, 'PATH_NOT_FOUND', f'Source not found: {source}'

        shutil.move(source, destination)
        return True, None, None

    result, err_code, err_msg = await loop.run_in_executor(None, _move)

    if err_code:
        if 'Permission' in (err_msg or ''):
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': err_msg, 'code': 'PERMISSION_DENIED'}, seq)
        else:
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': err_msg, 'code': err_code}, seq)
    else:
        resp = make_msg(MsgType.FILE_MANAGER, engine.client_id,
                        {'action': 'move', 'success': True,
                         'source': source, 'destination': destination}, seq)
    await engine.send_msg(resp)


async def _handle_copy(engine, payload, seq):
    """复制文件或目录。"""
    source = payload.get('source', '')
    destination = payload.get('destination', '')
    loop = asyncio.get_event_loop()

    def _copy():
        if not os.path.exists(source):
            return None, 'PATH_NOT_FOUND', f'Source not found: {source}'
        if os.path.exists(destination):
            return None, 'ALREADY_EXISTS', f'Destination already exists: {destination}'

        if os.path.isdir(source):
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
        return True, None, None

    result, err_code, err_msg = await loop.run_in_executor(None, _copy)

    if err_code:
        if 'Permission' in (err_msg or ''):
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': err_msg, 'code': 'PERMISSION_DENIED'}, seq)
        else:
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': err_msg, 'code': err_code}, seq)
    else:
        resp = make_msg(MsgType.FILE_MANAGER, engine.client_id,
                        {'action': 'copy', 'success': True,
                         'source': source, 'destination': destination}, seq)
    await engine.send_msg(resp)


async def _handle_mkdir(engine, payload, seq):
    """创建目录。"""
    path = payload.get('path', '')
    loop = asyncio.get_event_loop()

    def _mkdir():
        if os.path.exists(path):
            return None, 'ALREADY_EXISTS', f'Path already exists: {path}'
        os.makedirs(path, exist_ok=False)
        return True, None, None

    result, err_code, err_msg = await loop.run_in_executor(None, _mkdir)

    if err_code:
        if 'Permission' in (err_msg or ''):
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': err_msg, 'code': 'PERMISSION_DENIED'}, seq)
        else:
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': err_msg, 'code': err_code}, seq)
    else:
        resp = make_msg(MsgType.FILE_MANAGER, engine.client_id,
                        {'action': 'mkdir', 'success': True, 'path': path}, seq)
    await engine.send_msg(resp)


async def _handle_info(engine, payload, seq):
    """获取文件详细信息。"""
    path = payload.get('path', '')
    loop = asyncio.get_event_loop()

    def _info():
        if not os.path.exists(path):
            return None, 'PATH_NOT_FOUND', f'Path not found: {path}'

        st = os.stat(path)
        return _make_entry(os.path.basename(path), path, st, detailed=True), None, None

    result, err_code, err_msg = await loop.run_in_executor(None, _info)

    if err_code:
        if 'Permission' in (err_msg or ''):
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': err_msg, 'code': 'PERMISSION_DENIED'}, seq)
        else:
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': err_msg, 'code': err_code}, seq)
    else:
        resp = make_msg(MsgType.FILE_MANAGER, engine.client_id,
                        {'action': 'info', 'info': result}, seq)
    await engine.send_msg(resp)


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

_ACTION_MAP = {
    'list': _handle_list,
    'roots': _handle_roots,
    'search': _handle_search,
    'rename': _handle_rename,
    'delete': _handle_delete,
    'move': _handle_move,
    'copy': _handle_copy,
    'mkdir': _handle_mkdir,
    'info': _handle_info,
}


async def handle_file_manager(engine, msg):
    """处理文件管理指令。"""
    payload = msg.get('payload', {})
    action = payload.get('action', '')
    seq = msg.get('seq', 0)

    handler = _ACTION_MAP.get(action)
    if handler:
        try:
            await handler(engine, payload, seq)
        except PermissionError as e:
            logger.error(f'File manager permission error: {e}')
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': str(e), 'code': 'PERMISSION_DENIED'}, seq)
            await engine.send_msg(resp)
        except FileExistsError as e:
            logger.error(f'File manager already exists error: {e}')
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': str(e), 'code': 'ALREADY_EXISTS'}, seq)
            await engine.send_msg(resp)
        except FileNotFoundError as e:
            logger.error(f'File manager path not found error: {e}')
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': str(e), 'code': 'PATH_NOT_FOUND'}, seq)
            await engine.send_msg(resp)
        except Exception as e:
            logger.error(f'File manager handler error: {e}')
            resp = make_msg(MsgType.ERROR, engine.client_id,
                            {'error': str(e)}, seq)
            await engine.send_msg(resp)
    else:
        resp = make_msg(MsgType.ERROR, engine.client_id,
                        {'error': f'Unknown action: {action}'}, seq)
        await engine.send_msg(resp)
