import subprocess
import sys
import os
import tempfile
import traceback
import platform

def build_final():
    print("=" * 60)
    print("开始构建 MusicMetadataProcessor")
    print(f"Python版本: {sys.version}")
    print(f"系统架构: {platform.architecture()[0]}")
    print(f"工作目录: {os.getcwd()}")
    print("=" * 60)
    
    # 检查图标文件是否存在（支持多种路径）
    icon_paths = [
        "D:/moe-n/Desktop/app/icon.ico",
        "icon.ico",
        "./icon.ico",
        os.path.join(os.path.dirname(__file__), "icon.ico")
    ]
    
    icon_path = None
    for path in icon_paths:
        if os.path.exists(path):
            icon_path = path
            print(f"✅ 找到图标文件: {icon_path}")
            break
    
    if not icon_path:
        print("⚠️  警告: 未找到图标文件，将使用默认图标")
        icon_option = []
    else:
        print(f"✅ 使用图标: {icon_path}")
        icon_option = [f"--icon={icon_path}"]
    
    # 构建命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name=MusicMetadataProcessor",
        "--clean",
        "--noconfirm",
        
        # 添加图标参数（如果有）
        *icon_option,
        
        # 必需的隐藏导入
        "--hidden-import=flask",
        "--hidden-import=flask_cors",
        "--hidden-import=mutagen",
        "--hidden-import=requests",
        "--hidden-import=PySide6",
        "--hidden-import=PySide6.QtWidgets",
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui",
        
        "app_gui.py"
    ]
    
    print("开始构建...")
    print("命令:", " ".join(cmd))
    
    try:
        # 显示当前目录结构
        print("\n当前目录结构:")
        for root, dirs, files in os.walk('.'):
            level = root.replace('.', '').count(os.sep)
            indent = ' ' * 2 * level
            print(f'{indent}{os.path.basename(root)}/')
            subindent = ' ' * 2 * (level + 1)
            for file in files:
                if file.endswith(('.py', '.ico', '.txt')):
                    print(f'{subindent}{file}')
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        
        print("\n构建完成!")
        print("返回码:", result.returncode)
        
        if result.stdout:
            print("\n标准输出:")
            print(result.stdout[-1000:])  # 只显示最后1000字符避免日志过长
        
        if result.stderr:
            print("\n标准错误:")
            print(result.stderr[-1000:])  # 只显示最后1000字符
        
        # 检查构建是否成功
        if result.returncode == 0:
            dist_path = os.path.join("dist", "MusicMetadataProcessor.exe")
            if os.path.exists(dist_path):
                file_size = os.path.getsize(dist_path) / (1024*1024)
                print(f"\n✅ 构建成功！可执行文件位置: {dist_path}")
                print(f"文件大小: {file_size:.2f} MB")
                
                # 显示构建产物信息
                print("\n构建产物信息:")
                for root, dirs, files in os.walk('dist'):
                    for file in files:
                        if file.endswith('.exe'):
                            full_path = os.path.join(root, file)
                            size = os.path.getsize(full_path) / (1024*1024)
                            print(f"  {file}: {size:.2f} MB")
            else:
                print("\n❌ 构建完成但未找到可执行文件")
                # 检查整个目录结构
                print("当前目录的所有文件:")
                for root, dirs, files in os.walk('.'):
                    for file in files:
                        if file.endswith('.exe'):
                            print(f"找到EXE文件: {os.path.join(root, file)}")
                return 1
        else:
            print("\n❌ 构建失败！")
            return result.returncode
        
        return result.returncode
        
    except Exception as e:
        print(f"构建过程中发生错误: {e}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(build_final())
