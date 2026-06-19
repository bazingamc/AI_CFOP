"""
AI_CFOP - EXE打包脚本
使用方法: python build_exe.py
"""

import os
import sys
import shutil
import subprocess

APP_NAME = "AI_CFOP"
MAIN_SCRIPT = "cfop_analyzer_gui.py"
ICON_FILE = "./cube_ai_icon.ico"

EXCLUDE_MODULES = [
    "matplotlib", "numpy", "pandas", "scipy",
    "cv2", "opencv", "tensorflow", "torch", "keras",
    "selenium",
    "pytest",
    "IPython", "jupyter", "notebook",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
    "django", "flask", "fastapi",
    "sqlalchemy", "pymongo", "redis",
    "boto3", "botocore",
    "h5py", "tables",
]

HIDDEN_IMPORTS = [
    "openai",
    "httpx",
    "http",
    "h11",
    "anyio",
    "sniffio",
    "certifi",
    "idna",
    "h2",
    "hpack",
    "hyperframe",
    "hpack.struct",
    "hpack.hpack",
    "tkinter",
    "tkinter.ttk",
    "tkinter.scrolledtext",
    "tkinter.messagebox",
    "tkinter.filedialog",
    "tkinter.font",
    "tkwebview",
    "tkwebview.core",
]

def check_pyinstaller():
    try:
        import PyInstaller
        print(f"✓ PyInstaller 已安装 (版本: {PyInstaller.__version__})")
        return True
    except ImportError:
        print("✗ PyInstaller 未安装")
        return False

def check_upx():
    upx_paths = [
        "upx",
        "upx.exe",
        r"C:\Program Files\UPX\upx.exe",
        r"C:\UPX\upx.exe",
    ]
    
    for path in upx_paths:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✓ UPX 已安装: {path}")
                return path
        except:
            continue
    
    print("✗ UPX 未安装 (可选，用于进一步压缩)")
    print("  下载地址: https://github.com/upx/upx/releases")
    return None

def install_pyinstaller():
    print("\n正在安装 PyInstaller...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
    print("✓ PyInstaller 安装完成")

def clean_build():
    dirs_to_clean = ["build", "dist", "__pycache__"]
    files_to_clean = [f"{MAIN_SCRIPT}.spec"]
    
    for d in dirs_to_clean:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"✓ 清理目录: {d}")
    
    for f in files_to_clean:
        if os.path.exists(f):
            os.remove(f)
            print(f"✓ 清理文件: {f}")

def build_exe():
    print(f"\n{'='*50}")
    print(f"开始打包: {APP_NAME}")
    print(f"{'='*50}\n")
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--noconsole",
        "--name", APP_NAME,
        "--clean",
    ]
    
    if ICON_FILE and os.path.exists(ICON_FILE):
        cmd.extend(["--icon", ICON_FILE])
    
    upx_path = check_upx()
    if upx_path:
        upx_dir = os.path.dirname(upx_path)
        if not upx_dir:
            upx_dir = "."
        cmd.extend(["--upx-dir", upx_dir])
    
    for imp in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", imp])
    
    for mod in EXCLUDE_MODULES:
        cmd.extend(["--exclude-module", mod])
    
    # 打包 tkwebview 的 webview.dll（WebView2 嵌入浏览器所需）
    try:
        import tkwebview as _tw
        _tw_dir = os.path.dirname(_tw.__file__)
        _dll_src = os.path.join(_tw_dir, "platform", "win32", "x64", "webview.dll")
        if os.path.isfile(_dll_src):
            cmd.extend(["--add-binary", f"{_dll_src}{os.pathsep}tkwebview/platform/win32/x64"])
            print(f"  - 包含 webview.dll (tkwebview 嵌入浏览器)")
    except ImportError:
        print("  ⚠ tkwebview 未安装，csTimer 标签页将不可用")
    
    cmd.append(MAIN_SCRIPT)
    
    print(f"\n打包配置:")
    print(f"  - 文件夹模式 (onedir)")
    print(f"  - 无控制台窗口")
    print(f"  - 排除 {len(EXCLUDE_MODULES)} 个不需要的模块")
    print(f"  - 包含 {len(HIDDEN_IMPORTS)} 个必要模块")
    if upx_path:
        print(f"  - UPX压缩: 启用")
    print()
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print(f"\n{'='*50}")
        print("✓ 打包成功!")
        print(f"{'='*50}")
        
        dist_dir = os.path.join("dist", APP_NAME)
        exe_path = os.path.join(dist_dir, f"{APP_NAME}.exe")
        
        if os.path.exists(exe_path):
            config_file = os.path.join(dist_dir, ".cfop_config.json")
            with open(config_file, "w", encoding="utf-8") as f:
                f.write("{}")
            print(f"✓ 创建配置文件: .cfop_config.json")
            
            logs_dir = os.path.join(dist_dir, "logs")
            os.makedirs(logs_dir, exist_ok=True)
            print(f"✓ 创建日志目录: logs/")
            
            results_dir = os.path.join(dist_dir, "results")
            os.makedirs(results_dir, exist_ok=True)
            print(f"✓ 创建结果目录: results/")

            # 复制png目录（OLL/PLL图片、头像等）
            src_png = os.path.join(os.path.dirname(os.path.abspath(__file__)), "png")
            dst_png = os.path.join(dist_dir, "png")
            if os.path.isdir(src_png):
                if os.path.exists(dst_png):
                    shutil.rmtree(dst_png)
                shutil.copytree(src_png, dst_png)
                print(f"✓ 复制图片目录: png/")
            else:
                os.makedirs(os.path.join(dist_dir, "png", "avatars"), exist_ok=True)
                print(f"✓ 创建图片目录: png/")

            # 复制default_avatar.png
            src_avatar = os.path.join(os.path.dirname(os.path.abspath(__file__)), "default_avatar.png")
            dst_avatar = os.path.join(dist_dir, "default_avatar.png")
            if os.path.isfile(src_avatar):
                shutil.copy2(src_avatar, dst_avatar)
                print(f"✓ 复制默认头像: default_avatar.png")
            
            total_size = 0
            for root, dirs, files in os.walk(dist_dir):
                for f in files:
                    total_size += os.path.getsize(os.path.join(root, f))
            size_mb = total_size / (1024 * 1024)
            
            print(f"\n输出目录: {os.path.abspath(dist_dir)}")
            print(f"总大小: {size_mb:.2f} MB")
            
            print(f"\n目录结构:")
            print(f"  {APP_NAME}/")
            print(f"  ├── {APP_NAME}.exe")
            print(f"  ├── .cfop_config.json")
            print(f"  ├── logs/")
            print(f"  ├── results/")
            print(f"  └── _internal/  (运行库)")
            
            print("\n使用说明:")
            print(f"1. 将 {APP_NAME} 文件夹复制到任意位置")
            print("2. 双击 exe 文件运行")
            print("3. 配置和日志会保存在同目录下")
    else:
        print(f"\n✗ 打包失败，错误码: {result.returncode}")
        return False
    
    return True

def main():
    print(f"\n{'='*50}")
    print(f"  {APP_NAME} - 打包工具")
    print(f"{'='*50}\n")
    
    if not check_pyinstaller():
        try:
            install_pyinstaller()
        except Exception as e:
            print(f"✗ 安装 PyInstaller 失败: {e}")
            print("\n请手动安装: pip install pyinstaller")
            return
    
    print("\n清理旧的构建文件...")
    clean_build()
    
    if build_exe():
        print("\n打包完成!")

if __name__ == "__main__":
    main()
