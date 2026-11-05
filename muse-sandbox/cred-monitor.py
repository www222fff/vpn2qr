#!/usr/bin/env python3
"""Monitor: restart proxy-fwd.py every 2 minutes to pick up fresh credentials.
Run this in background. It keeps the forwarder using current HTTPS_PROXY.
"""
import os, signal, time, subprocess

def get_fwd_pid():
    for line in subprocess.run(['ps','-eo','pid,args'],capture_output=True,text=True).stdout.split('\n'):
        if 'proxy-fwd.py' in line and 'monitor' not in line:
            try:
                return int(line.strip().split()[0])
            except: pass
    return None

def start_fwd():
    os.chdir('/home/hatch/workspace/xray-node')
    subprocess.Popen(['python3','proxy-fwd.py'],stdout=open('proxy-fwd.log','w'),stderr=subprocess.STDOUT)

while True:
    time.sleep(60)  # 1 minute
    pid = get_fwd_pid()
    if pid:
        try: os.kill(pid, signal.SIGTERM)
        except: pass
        time.sleep(2)
    start_fwd()
    print(f"[{time.strftime('%H:%M:%S')}] forwarder refreshed", flush=True)
