"""
AI_CFOP - EXE打包 & 安装包构建脚本
使用方法:
- python build_exe.py — 打包 EXE + 构建安装包（默认）
- python build_exe.py --exe-only — 仅打包 EXE
- python build_exe.py --installer-only — 仅构建安装包（跳过EXE打包）
"""

import os
import sys
import shutil
import subprocess
import argparse
import re

APP_NAME = "AI_CFOP"
MAIN_SCRIPT = "cfop_analyzer_gui.py"
ICON_FILE = "./cube_ai_icon.ico"
ISS_FILE = "./installer.iss"
INSTALLER_OUTPUT_DIR = "installer_output"

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

            # 复制.cfop_op_algo.json（OLL/PLL公式选择配置）
            src_algo = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cfop_op_algo.json")
            dst_algo = os.path.join(dist_dir, ".cfop_op_algo.json")
            if os.path.isfile(src_algo):
                shutil.copy2(src_algo, dst_algo)
                print(f"✓ 复制公式配置: .cfop_op_algo.json")
            
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

def get_version():
    """从 config.py 读取版本号（唯一版本源）"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', content)
    if m:
        return m.group(1)
    print("✗ 无法从 config.py 读取 APP_VERSION")
    return None

def update_iss_version(version):
    """将版本号写入 installer.iss"""
    if not os.path.isfile(ISS_FILE):
        print(f"✗ 未找到 {ISS_FILE}")
        return False
    with open(ISS_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(
        r'#define\s+MyAppVersion\s+"[^"]*"',
        f'#define MyAppVersion "{version}"',
        content
    )
    with open(ISS_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✓ installer.iss 版本号已更新为 {version}")
    return True

def find_inno_setup():
    """查找 Inno Setup 编译器路径"""
    # 1. 常见安装路径（C盘和F盘等）
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        r"C:\Program Files\Inno Setup 5\ISCC.exe",
        r"D:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"D:\Program Files\Inno Setup 6\ISCC.exe",
        r"E:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"E:\Program Files\Inno Setup 6\ISCC.exe",
        r"F:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"F:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    # 2. 通过注册表查找卸载信息获取安装路径
    try:
        import winreg
        for hive in [winreg.HKLM, winreg.HKCU]:
            try:
                key = winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Uninstall", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey = winreg.OpenKey(key, subkey_name)
                        try:
                            display_name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                            if "Inno Setup" in display_name:
                                install_loc, _ = winreg.QueryValueEx(subkey, "InstallLocation")
                                if install_loc:
                                    iscc = os.path.join(install_loc, "ISCC.exe")
                                    if os.path.isfile(iscc):
                                        winreg.CloseKey(subkey)
                                        winreg.CloseKey(key)
                                        return iscc
                        except FileNotFoundError:
                            pass
                        winreg.CloseKey(subkey)
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except OSError:
                pass
    except ImportError:
        pass

    # 3. 尝试 PATH 中查找
    try:
        result = subprocess.run(["ISCC", "/?"], capture_output=True, text=True)
        if result.returncode == 0:
            return "ISCC"
    except FileNotFoundError:
        pass

    return None

def build_installer():
    """使用 Inno Setup 构建安装包"""
    print(f"\n{'='*50}")
    print(f"开始构建安装包: {APP_NAME}")
    print(f"{'='*50}\n")

    # 检查 dist 目录是否存在
    dist_dir = os.path.join("dist", APP_NAME)
    if not os.path.isdir(dist_dir):
        print("✗ 未找到打包输出目录 dist/AI_CFOP，请先运行打包")
        return False

    # 检查 ISS 文件
    if not os.path.isfile(ISS_FILE):
        print(f"✗ 未找到安装脚本: {ISS_FILE}")
        return False

    # 查找 Inno Setup
    iscc_path = find_inno_setup()
    if not iscc_path:
        print("✗ 未找到 Inno Setup")
        print("  请下载安装: https://jrsoftware.org/isdl.php")
        return False
    print(f"✓ Inno Setup: {iscc_path}")

    # 创建输出目录
    os.makedirs(INSTALLER_OUTPUT_DIR, exist_ok=True)

    # 编译安装包
    cmd = [iscc_path, ISS_FILE]
    print(f"\n正在编译安装包...")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        version = get_version() or "unknown"
        installer_name = f"AI_CFOP_Setup_{version}.exe"
        installer_path = os.path.join(INSTALLER_OUTPUT_DIR, installer_name)

        if os.path.isfile(installer_path):
            size_mb = os.path.getsize(installer_path) / (1024 * 1024)
            print(f"\n{'='*50}")
            print("✓ 安装包构建成功!")
            print(f"{'='*50}")
            print(f"  文件: {os.path.abspath(installer_path)}")
            print(f"  大小: {size_mb:.2f} MB")
            print(f"\n安装包功能:")
            print("  - 首次安装: 选择目录，完整安装")
            print("  - 覆盖安装: 自动检测已安装目录，仅更新程序文件")
            print("  - 保留数据: 配置、数据库、日志、结果、头像不会被覆盖")
        else:
            # 尝试在输出目录中找到生成的文件
            files = [f for f in os.listdir(INSTALLER_OUTPUT_DIR) if f.endswith('.exe')]
            if files:
                print(f"\n✓ 安装包构建成功!")
                print(f"  文件: {os.path.abspath(os.path.join(INSTALLER_OUTPUT_DIR, files[0]))}")
            else:
                print(f"\n⚠ 编译成功但未找到安装包文件，请检查 {INSTALLER_OUTPUT_DIR}/ 目录")
        return True
    else:
        print(f"\n✗ 安装包构建失败，错误码: {result.returncode}")
        return False

def main():
    parser = argparse.ArgumentParser(description=f"{APP_NAME} - 打包工具")
    parser.add_argument("--exe-only", action="store_true", help="仅打包EXE，不构建安装包")
    parser.add_argument("--installer-only", action="store_true", help="仅构建安装包（跳过EXE打包）")
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print(f"  {APP_NAME} - 打包工具")
    print(f"{'='*50}\n")

    # 从 config.py 读取版本号并同步到 installer.iss
    version = get_version()
    if version:
        print(f"✓ 当前版本: {version}")
        update_iss_version(version)
    else:
        print("⚠ 无法读取版本号，installer.iss 版本号未更新")

    if args.installer_only:
        # 仅构建安装包
        if build_installer():
            print("\n安装包构建完成!")
        return

    # 打包 EXE
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
        # 默认继续构建安装包，除非指定 --exe-only
        if not args.exe_only:
            if build_installer():
                print("\n全部完成! (EXE打包 + 安装包构建)")
            else:
                print("\nEXE打包完成，但安装包构建失败")

if __name__ == "__main__":
    main()
