"""
Port Manager - Windows 端口可视化管理工具
一个本地桌面应用，查看端口占用、搜索过滤、一键Kill进程。
"""

import os
import subprocess
import re

import psutil
import webview


def get_connections():
    """通过 netstat -ano 获取所有网络连接，再用 psutil 查进程名"""
    results = []
    try:
        output = subprocess.check_output(
            ['netstat', '-ano'], encoding='gbk', errors='replace'
        )
    except Exception as e:
        return [{'error': str(e)}]

    pid_name_cache = {}

    for line in output.splitlines():
        line = line.strip()
        # 匹配 TCP / UDP 行
        m = re.match(
            r'(TCP|UDP)\s+'           # 协议
            r'(\S+):(\d+)\s+'         # 本地地址:端口
            r'(\S+):(\S+)\s*'         # 远程地址:端口
            r'(\S*)\s*'               # 状态 (UDP 无状态)
            r'(\d+)',                  # PID
            line
        )
        if not m:
            continue

        proto = m.group(1)
        local_addr = m.group(2)
        local_port = int(m.group(3))
        remote_addr = m.group(4)
        remote_port_str = m.group(5)
        status = m.group(6).strip() if m.group(6) else ''
        pid = int(m.group(7))

        remote_port = int(remote_port_str) if remote_port_str.isdigit() else 0

        # netstat 输出状态名与 psutil 不同，统一一下
        status_map = {
            'LISTENING': 'LISTEN',
            'ESTABLISHED': 'ESTABLISHED',
            'TIME_WAIT': 'TIME_WAIT',
            'CLOSE_WAIT': 'CLOSE_WAIT',
            'FIN_WAIT_2': 'FIN_WAIT2',
            'SYN_SENT': 'SYN_SENT',
            'SYN_RECEIVED': 'SYN_RECV',
            'LAST_ACK': 'LAST_ACK',
            'CLOSING': 'CLOSING',
        }
        status = status_map.get(status, status)

        # 获取进程名（带缓存）
        proc_name = ''
        if pid > 0:
            if pid in pid_name_cache:
                proc_name = pid_name_cache[pid]
            else:
                try:
                    proc_name = psutil.Process(pid).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    proc_name = '-'
                pid_name_cache[pid] = proc_name

        results.append({
            'proto': proto,
            'localAddr': local_addr,
            'localPort': local_port,
            'remoteAddr': remote_addr,
            'remotePort': remote_port,
            'status': status,
            'pid': pid,
            'procName': proc_name,
        })

    return results


def kill_process(pid):
    """终止指定PID的进程"""
    try:
        pid = int(pid)
        if pid <= 0:
            return {'success': False, 'message': '无效的 PID'}
        if pid == os.getpid():
            return {'success': False, 'message': '不能终止自身进程'}
        proc = psutil.Process(pid)
        proc_name = proc.name()
        proc.kill()
        proc.wait(timeout=3)
        return {'success': True, 'message': f'已终止进程 {proc_name} (PID: {pid})'}
    except psutil.NoSuchProcess:
        return {'success': False, 'message': f'进程 {pid} 不存在'}
    except psutil.AccessDenied:
        # 降级用 taskkill
        try:
            subprocess.check_output(
                ['taskkill', '/F', '/PID', str(pid)],
                encoding='gbk', errors='replace'
            )
            return {'success': True, 'message': f'已终止进程 (PID: {pid})'}
        except Exception:
            return {'success': False, 'message': f'无权限终止进程 {pid}，请以管理员身份运行'}
    except Exception as e:
        return {'success': False, 'message': f'终止失败: {str(e)}'}


class Api:
    """暴露给前端 JS 调用的 Python API"""

    def get_ports(self):
        return get_connections()

    def kill_pid(self, pid):
        return kill_process(pid)


HTML = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Port Manager</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Noto+Sans+SC:wght@300;400;500;700&display=swap');

  * { margin: 0; padding: 0; box-sizing: border-box; }

  :root {
    --bg-primary: #f5f6fa;
    --bg-surface: #ffffff;
    --bg-toolbar: #ffffff;
    --bg-input: #f0f1f5;
    --bg-row-hover: #eef0ff;
    --bg-row-stripe: #fafbfd;
    --border: #e2e4ea;
    --border-focus: #5b6ef5;
    --text-primary: #1a1d2e;
    --text-secondary: #5a5e72;
    --text-muted: #9498ab;
    --accent: #5b6ef5;
    --accent-light: #eef0ff;
    --danger: #e5354b;
    --danger-hover: #ff4d63;
    --danger-bg: #fef2f2;
    --success: #10b981;
    --success-bg: #ecfdf5;
    --listening: #10b981;
    --established: #3b82f6;
    --time-wait: #f59e0b;
    --close-wait: #f97316;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
  }

  html, body {
    height: 100%;
    font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }

  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }

  /* ---- Toolbar ---- */
  .toolbar {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 14px 20px;
    background: var(--bg-toolbar);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    box-shadow: var(--shadow-sm);
    position: relative;
    z-index: 20;
  }

  .toolbar .logo {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-right: 6px;
    flex-shrink: 0;
  }

  .toolbar .logo svg { width: 22px; height: 22px; color: var(--accent); }

  .toolbar .logo span {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    font-size: 14px;
    letter-spacing: 0.5px;
    color: var(--text-primary);
  }

  .search-box {
    flex: 1;
    position: relative;
    max-width: 480px;
  }

  .search-box svg {
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    width: 16px; height: 16px;
    color: var(--text-muted);
    pointer-events: none;
    transition: color 0.2s;
  }

  .search-box input {
    width: 100%;
    padding: 9px 12px 9px 36px;
    background: var(--bg-input);
    border: 1.5px solid transparent;
    border-radius: 10px;
    color: var(--text-primary);
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    outline: none;
    transition: all 0.2s;
  }

  .search-box input:focus {
    border-color: var(--border-focus);
    background: #fff;
    box-shadow: 0 0 0 3px rgba(91,110,245,0.12);
  }

  .search-box input:focus + svg { color: var(--accent); }

  .search-box input::placeholder { color: var(--text-muted); }

  .toolbar-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-left: auto;
    flex-shrink: 0;
  }

  .btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 14px;
    border: 1.5px solid var(--border);
    border-radius: 8px;
    background: #fff;
    color: var(--text-secondary);
    font-family: 'Noto Sans SC', sans-serif;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }

  .btn:hover {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-light);
  }

  .btn:active { transform: scale(0.97); }

  .btn svg { width: 14px; height: 14px; }

  .auto-refresh {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .toggle {
    position: relative;
    width: 36px; height: 20px;
    appearance: none;
    background: var(--bg-input);
    border: 1.5px solid var(--border);
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.25s;
    flex-shrink: 0;
  }

  .toggle::after {
    content: '';
    position: absolute;
    top: 2px; left: 2px;
    width: 14px; height: 14px;
    background: var(--text-muted);
    border-radius: 50%;
    transition: all 0.25s;
  }

  .toggle:checked { background: var(--accent); border-color: var(--accent); }
  .toggle:checked::after { left: 18px; background: #fff; }

  /* ---- Stats Bar ---- */
  .stats-bar {
    display: flex;
    align-items: center;
    gap: 22px;
    padding: 8px 20px;
    border-bottom: 1px solid var(--border);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-muted);
    flex-shrink: 0;
    background: var(--bg-surface);
  }

  .stats-bar .stat { display: flex; align-items: center; gap: 6px; }
  .stats-bar .stat .dot { width: 7px; height: 7px; border-radius: 50%; }
  .stat-total .dot { background: var(--accent); }
  .stat-listening .dot { background: var(--listening); }
  .stat-established .dot { background: var(--established); }
  .stat-other .dot { background: var(--text-muted); }
  .stats-bar .stat-val { color: var(--text-primary); font-weight: 600; }

  /* ---- Table ---- */
  .table-wrap {
    flex: 1;
    overflow: auto;
    background: var(--bg-surface);
  }

  .table-wrap::-webkit-scrollbar { width: 8px; height: 8px; }
  .table-wrap::-webkit-scrollbar-track { background: var(--bg-primary); }
  .table-wrap::-webkit-scrollbar-thumb { background: #cccfda; border-radius: 4px; }
  .table-wrap::-webkit-scrollbar-thumb:hover { background: #b0b4c2; }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12.5px;
    table-layout: fixed;
  }

  thead { position: sticky; top: 0; z-index: 10; }

  th {
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: var(--text-muted);
    background: var(--bg-primary);
    border-bottom: 1.5px solid var(--border);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
    transition: color 0.15s;
  }

  th:hover { color: var(--text-primary); }

  th .sort-arrow {
    display: inline-block;
    margin-left: 3px;
    opacity: 0;
    transition: opacity 0.15s;
    font-size: 10px;
  }

  th.sorted .sort-arrow { opacity: 1; color: var(--accent); }
  th.sorted { color: var(--accent); }

  /* Column widths */
  th:nth-child(1), td:nth-child(1) { width: 56px; }
  th:nth-child(2), td:nth-child(2) { width: 130px; }
  th:nth-child(3), td:nth-child(3) { width: 80px; }
  th:nth-child(4), td:nth-child(4) { width: 130px; }
  th:nth-child(5), td:nth-child(5) { width: 80px; }
  th:nth-child(6), td:nth-child(6) { width: 120px; }
  th:nth-child(7), td:nth-child(7) { width: 68px; }
  th:nth-child(8), td:nth-child(8) { width: auto; }
  th:nth-child(9), td:nth-child(9) { width: 72px; text-align: center; }

  td {
    padding: 7px 14px;
    border-bottom: 1px solid #f0f1f5;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  tr:nth-child(even) td { background: var(--bg-row-stripe); }
  tr:hover td { background: var(--bg-row-hover); color: var(--text-primary); }

  /* Status badges */
  .status-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 5px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.4px;
  }

  .status-LISTEN { background: #ecfdf5; color: var(--listening); }
  .status-ESTABLISHED { background: #eff6ff; color: var(--established); }
  .status-TIME_WAIT { background: #fffbeb; color: var(--time-wait); }
  .status-CLOSE_WAIT { background: #fff7ed; color: var(--close-wait); }
  .status-NONE, .status-other { background: var(--bg-input); color: var(--text-muted); }

  .proc-name { color: var(--text-primary); font-weight: 500; }
  .port-highlight { color: var(--accent); font-weight: 700; }

  /* Kill button */
  .btn-kill {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 4px 10px;
    border: 1px solid #fecaca;
    border-radius: 6px;
    background: var(--danger-bg);
    color: var(--danger);
    font-family: 'Noto Sans SC', sans-serif;
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .btn-kill:hover {
    background: #fee2e2;
    border-color: var(--danger);
    transform: translateY(-1px);
    box-shadow: 0 2px 6px rgba(229,53,75,0.15);
  }

  .btn-kill svg { width: 12px; height: 12px; }
  .btn-kill:disabled { opacity: 0.3; cursor: not-allowed; transform: none; box-shadow: none; }

  /* ---- Toast ---- */
  .toast-container {
    position: fixed;
    top: 16px;
    right: 16px;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .toast {
    padding: 10px 16px;
    border-radius: 10px;
    font-size: 12px;
    font-weight: 500;
    animation: toastIn 0.25s ease-out, toastOut 0.25s ease-in 2.7s forwards;
    max-width: 360px;
    box-shadow: var(--shadow-md);
  }

  .toast-success { background: var(--success-bg); color: #065f46; border: 1px solid #a7f3d0; }
  .toast-error { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
  .toast-info { background: var(--accent-light); color: #3730a3; border: 1px solid #c7d2fe; }

  @keyframes toastIn { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
  @keyframes toastOut { from { opacity: 1; } to { opacity: 0; } }

  /* ---- Modal ---- */
  .modal-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.25);
    backdrop-filter: blur(3px);
    z-index: 900;
    align-items: center;
    justify-content: center;
  }

  .modal-overlay.active { display: flex; }

  .modal {
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 24px;
    min-width: 380px;
    box-shadow: 0 12px 40px rgba(0,0,0,0.12);
    animation: modalIn 0.2s ease-out;
  }

  @keyframes modalIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }

  .modal h3 { font-size: 15px; font-weight: 600; margin-bottom: 8px; }
  .modal p { font-size: 13px; color: var(--text-secondary); margin-bottom: 20px; line-height: 1.6; }
  .modal p strong { color: var(--danger); }

  .modal-actions { display: flex; gap: 10px; justify-content: flex-end; }

  .modal-actions .btn-cancel {
    padding: 8px 18px;
    border: 1.5px solid var(--border);
    border-radius: 8px;
    background: #fff;
    color: var(--text-secondary);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s;
  }

  .modal-actions .btn-cancel:hover { border-color: var(--text-muted); color: var(--text-primary); }

  .modal-actions .btn-confirm-kill {
    padding: 8px 18px;
    border: none;
    border-radius: 8px;
    background: var(--danger);
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
  }

  .modal-actions .btn-confirm-kill:hover { background: var(--danger-hover); }

  /* ---- Empty ---- */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px 20px;
    color: var(--text-muted);
  }

  .empty-state svg { width: 48px; height: 48px; margin-bottom: 16px; opacity: 0.35; }
  .empty-state p { font-size: 14px; }

  /* ---- Loading ---- */
  .loading-bar {
    height: 2.5px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    position: absolute;
    top: 0; left: 0; right: 0;
    animation: loadSlide 0.9s ease-in-out infinite;
    display: none;
    z-index: 30;
  }

  .loading-bar.active { display: block; }

  @keyframes loadSlide { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }

  mark {
    background: rgba(91,110,245,0.18);
    color: var(--text-primary);
    border-radius: 2px;
    padding: 0 2px;
  }
</style>
</head>
<body>
<div class="app">
  <div class="loading-bar" id="loadingBar"></div>

  <div class="toolbar">
    <div class="logo">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
      </svg>
      <span>PORT MANAGER</span>
    </div>

    <div class="search-box">
      <input type="text" id="searchInput" placeholder="搜索端口、PID、进程名 ..." autofocus />
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
      </svg>
    </div>

    <div class="toolbar-actions">
      <button class="btn" onclick="refreshData()" title="Ctrl+R">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
        </svg>
        刷新
      </button>
      <div class="auto-refresh">
        <input type="checkbox" class="toggle" id="autoRefreshToggle" />
        <label for="autoRefreshToggle" style="cursor:pointer;">自动刷新</label>
      </div>
    </div>
  </div>

  <div class="stats-bar">
    <div class="stat stat-total"><span class="dot"></span>总计 <span class="stat-val" id="statTotal">0</span></div>
    <div class="stat stat-listening"><span class="dot"></span>LISTEN <span class="stat-val" id="statListening">0</span></div>
    <div class="stat stat-established"><span class="dot"></span>ESTABLISHED <span class="stat-val" id="statEstablished">0</span></div>
    <div class="stat stat-other"><span class="dot"></span>其他 <span class="stat-val" id="statOther">0</span></div>
    <div style="margin-left:auto;" id="lastRefresh"></div>
  </div>

  <div class="table-wrap" id="tableWrap">
    <table>
      <thead>
        <tr>
          <th data-col="proto" data-type="str">协议 <span class="sort-arrow"></span></th>
          <th data-col="localAddr" data-type="str">本地地址 <span class="sort-arrow"></span></th>
          <th data-col="localPort" data-type="num">本地端口 <span class="sort-arrow"></span></th>
          <th data-col="remoteAddr" data-type="str">远程地址 <span class="sort-arrow"></span></th>
          <th data-col="remotePort" data-type="num">远程端口 <span class="sort-arrow"></span></th>
          <th data-col="status" data-type="str">状态 <span class="sort-arrow"></span></th>
          <th data-col="pid" data-type="num">PID <span class="sort-arrow"></span></th>
          <th data-col="procName" data-type="str">进程名 <span class="sort-arrow"></span></th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody id="tableBody"></tbody>
    </table>
  </div>
</div>

<div class="toast-container" id="toastContainer"></div>

<div class="modal-overlay" id="killModal">
  <div class="modal">
    <h3>确认终止进程</h3>
    <p id="killModalMsg"></p>
    <div class="modal-actions">
      <button class="btn-cancel" onclick="closeKillModal()">取消</button>
      <button class="btn-confirm-kill" id="btnConfirmKill">终止进程</button>
    </div>
  </div>
</div>

<script>
  let allData = [];
  let sortCol = 'localPort';
  let sortDir = 'asc';
  let autoRefreshTimer = null;
  let pendingKillPid = null;

  async function fetchPorts() {
    return await window.pywebview.api.get_ports();
  }

  async function killPid(pid) {
    return await window.pywebview.api.kill_pid(pid);
  }

  function showToast(msg, type) {
    const c = document.getElementById('toastContainer');
    const t = document.createElement('div');
    t.className = 'toast toast-' + (type || 'info');
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => t.remove(), 3000);
  }

  async function refreshData() {
    document.getElementById('loadingBar').classList.add('active');
    try {
      allData = await fetchPorts();
      renderTable();
      updateStats();
      document.getElementById('lastRefresh').textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN');
    } catch (e) {
      showToast('获取数据失败: ' + e, 'error');
    } finally {
      document.getElementById('loadingBar').classList.remove('active');
    }
  }

  function updateStats() {
    const d = getFilteredData();
    const l = d.filter(r => r.status === 'LISTEN').length;
    const e = d.filter(r => r.status === 'ESTABLISHED').length;
    document.getElementById('statTotal').textContent = d.length;
    document.getElementById('statListening').textContent = l;
    document.getElementById('statEstablished').textContent = e;
    document.getElementById('statOther').textContent = d.length - l - e;
  }

  function getSearchTerm() { return document.getElementById('searchInput').value.trim().toLowerCase(); }

  function matchRow(row, term) {
    if (!term) return true;
    const f = [row.proto, row.localAddr, String(row.localPort), row.remoteAddr, String(row.remotePort), row.status, String(row.pid), row.procName];
    return f.some(v => v.toLowerCase().includes(term));
  }

  function getFilteredData() { return allData.filter(r => matchRow(r, getSearchTerm())); }

  function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

  function hl(text, term) {
    if (!term || !text) return esc(String(text));
    const s = String(text), i = s.toLowerCase().indexOf(term);
    if (i === -1) return esc(s);
    return esc(s.substring(0, i)) + '<mark>' + esc(s.substring(i, i + term.length)) + '</mark>' + esc(s.substring(i + term.length));
  }

  function sortData(data) {
    const col = sortCol, dir = sortDir === 'asc' ? 1 : -1;
    const th = document.querySelector('th[data-col="' + col + '"]');
    const isNum = th && th.dataset.type === 'num';
    return [...data].sort((a, b) => {
      let va = a[col], vb = b[col];
      if (isNum) return ((Number(va)||0) - (Number(vb)||0)) * dir;
      return String(va).toLowerCase().localeCompare(String(vb).toLowerCase()) * dir;
    });
  }

  function renderTable() {
    const tbody = document.getElementById('tableBody');
    const term = getSearchTerm();
    let data = sortData(getFilteredData());

    if (!data.length) {
      tbody.innerHTML = '<tr><td colspan="9"><div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg><p>' + (term ? '没有匹配 "' + esc(term) + '" 的结果' : '没有活动连接') + '</p></div></td></tr>';
      updateStats();
      return;
    }

    tbody.innerHTML = data.map(r => {
      const sc = ['LISTEN','ESTABLISHED','TIME_WAIT','CLOSE_WAIT','NONE'].includes(r.status) ? 'status-'+r.status : 'status-other';
      const dis = r.pid <= 0 ? 'disabled' : '';
      return '<tr>'
        + '<td>' + hl(r.proto, term) + '</td>'
        + '<td>' + hl(r.localAddr, term) + '</td>'
        + '<td class="port-highlight">' + hl(r.localPort, term) + '</td>'
        + '<td>' + hl(r.remoteAddr||'-', term) + '</td>'
        + '<td>' + hl(r.remotePort||'-', term) + '</td>'
        + '<td><span class="status-badge '+sc+'">' + hl(r.status||'-', term) + '</span></td>'
        + '<td>' + hl(r.pid, term) + '</td>'
        + '<td class="proc-name">' + hl(r.procName||'-', term) + '</td>'
        + '<td style="text-align:center"><button class="btn-kill" '+dis+' onclick="confirmKill('+r.pid+',\''+esc(r.procName).replace(/'/g,"\\'")+'\')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg> Kill</button></td>'
        + '</tr>';
    }).join('');
    updateStats();
  }

  function confirmKill(pid, name) {
    pendingKillPid = pid;
    document.getElementById('killModalMsg').innerHTML = '确定要终止进程 <strong>'+esc(name)+'</strong> (PID: <strong>'+pid+'</strong>) 吗？';
    document.getElementById('killModal').classList.add('active');
  }

  function closeKillModal() {
    document.getElementById('killModal').classList.remove('active');
    pendingKillPid = null;
  }

  document.getElementById('btnConfirmKill').addEventListener('click', async () => {
    if (pendingKillPid === null) return;
    const pid = pendingKillPid;
    closeKillModal();
    try {
      const r = await killPid(pid);
      showToast(r.message, r.success ? 'success' : 'error');
      if (r.success) setTimeout(refreshData, 500);
    } catch (e) { showToast('操作失败: '+e, 'error'); }
  });

  document.querySelectorAll('th[data-col]').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (sortCol === col) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
      else { sortCol = col; sortDir = 'asc'; }
      document.querySelectorAll('th').forEach(h => h.classList.remove('sorted'));
      th.classList.add('sorted');
      th.querySelector('.sort-arrow').textContent = sortDir === 'asc' ? '▲' : '▼';
      renderTable();
    });
  });

  document.getElementById('searchInput').addEventListener('input', renderTable);

  document.getElementById('autoRefreshToggle').addEventListener('change', e => {
    if (e.target.checked) {
      autoRefreshTimer = setInterval(refreshData, 3000);
      showToast('已开启自动刷新 (3秒)', 'info');
    } else {
      clearInterval(autoRefreshTimer);
      showToast('已关闭自动刷新', 'info');
    }
  });

  document.addEventListener('keydown', e => {
    if ((e.ctrlKey && e.key === 'r') || e.key === 'F5') { e.preventDefault(); refreshData(); }
    if (e.ctrlKey && e.key === 'f') { e.preventDefault(); document.getElementById('searchInput').focus(); document.getElementById('searchInput').select(); }
    if (e.key === 'Escape') {
      if (document.getElementById('killModal').classList.contains('active')) closeKillModal();
      else { document.getElementById('searchInput').value = ''; renderTable(); }
    }
  });

  window.addEventListener('pywebviewready', refreshData);
</script>
</body>
</html>
"""


def main():
    api = Api()
    window = webview.create_window(
        'Port Manager',
        html=HTML,
        js_api=api,
        width=1100,
        height=720,
        min_size=(800, 500),
        background_color='#f5f6fa',
    )
    webview.start(debug=False)


if __name__ == '__main__':
    main()
