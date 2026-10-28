import os
import sys
import subprocess
import time
import webbrowser

def main():
    # 获取项目根目录
    project_root = os.path.dirname(os.path.abspath(__file__))
    server_dir = os.path.join(project_root, 'server')
    web_dir = os.path.join(project_root, 'web')

    print(f"Project Root: {project_root}")
    print("Preparing to launch services...")

    # Windows 启动命令
    if sys.platform == 'win32':
        # 启动后端
        print(">> Launching Backend (Port 8000)...")
        subprocess.Popen(f'start "PyCollar Backend" cmd /k "python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"', 
                         shell=True, cwd=server_dir)
        
        # 启动前端
        print(">> Launching Frontend (Port 5173)...")
        subprocess.Popen(f'start "PyCollar Frontend" cmd /k "npm run dev"', 
                         shell=True, cwd=web_dir)
    else:
        # Mac/Linux (简单适配)
        print(">> Launching Backend...")
        subprocess.Popen(['python3', '-m', 'uvicorn', 'main:app', '--reload'], cwd=server_dir)
        print(">> Launching Frontend...")
        subprocess.Popen(['npm', 'run', 'dev'], cwd=web_dir)

    print("\nServices launched in new windows.")
    print("Backend API: http://localhost:8000")
    print("Frontend UI: http://localhost:5173")
    
    # 等待服务启动后打开浏览器
    print("Opening browser in 3 seconds...")
    time.sleep(3)
    webbrowser.open("http://localhost:5173")

if __name__ == "__main__":
    main()
