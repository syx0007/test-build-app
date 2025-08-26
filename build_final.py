import subprocess
import sys
import os
import tempfile

def build_final():
    # 检查图标文件是否存在
    icon_paths = [
        "icon.ico",
        "./icon.ico",
        "../icon.ico",
        "resources/icon.ico",
        "assets/icon.ico"
    ]
    
    icon_path = None
    for path in icon_paths:
        if os.path.exists(path):
            icon_path = path
            break
    
    if icon_path is None:
        print("警告: 未找到图标文件，将继续不使用图标")
        icon_option = []
    else:
        print(f"使用图标: {icon_path}")
        icon_option = [f"--icon={icon_path}"]
    
    # 创建临时目录并复制图标文件
    temp_dir = tempfile.mkdtemp()
    temp_icon_path = os.path.join(temp_dir, "icon.ico")
    
    try:
        # 使用文件读取和写入的方式复制图标，避免文件占用问题
        with open(icon_path, 'rb') as src:
            with open(temp_icon_path, 'wb') as dst:
                dst.write(src.read())
        
        icon_option = [f"--icon={temp_icon_path}"]
        print(f"使用图标: {icon_path}")
        
        # 添加数据文件选项，将图标文件打包到exe中
        add_data_option = ["--add-data", f"{temp_icon_path};."]
        
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--windowed",
            "--name=MusicMetadataProcessor",
            "--clean",
            "--noconfirm",
            
            # 添加图标参数
            *icon_option,
            
            # 添加数据文件
            *add_data_option,
            
            # 必需的隐藏导入 - 更新了所有必要的库
            "--hidden-import=flask",
            "--hidden-import=flask_cors",
            "--hidden-import=mutagen",
            "--hidden-import=mutagen.id3",
            "--hidden-import=mutagen.mp3",
            "--hidden-import=mutagen.flac",
            "--hidden-import=mutagen.oggvorbis",
            "--hidden-import=mutagen.mp4",
            "--hidden-import=mutagen.wave",
            "--hidden-import=mutagen.aiff",
            "--hidden-import=requests",
            "--hidden-import=requests.adapters",
            "--hidden-import=urllib3",
            "--hidden-import=urllib3.util",
            "--hidden-import=urllib3.util.retry",
            "--hidden-import=urllib3.util.connection",
            "--hidden-import=urllib3.contrib",
            "--hidden-import=urllib3.contrib.pyopenssl",
            "--hidden-import=PySide6",
            "--hidden-import=PySide6.QtWidgets",
            "--hidden-import=PySide6.QtCore",
            "--hidden-import=PySide6.QtGui",
            "--hidden-import=http.client",
            "--hidden-import=charset_normalizer",
            "--hidden-import=idna",
            "--hidden-import=email",
            "--hidden-import=email.mime",
            "--hidden-import=email.mime.text",
            "--hidden-import=email.mime.multipart",
            "--hidden-import=OpenSSL",
            "--hidden-import=OpenSSL.SSL",
            "--hidden-import=OpenSSL.crypto",
            "--hidden-import=cryptography",
            "--hidden-import=cryptography.hazmat",
            "--hidden-import=cryptography.hazmat.backends",
            "--hidden-import=cryptography.hazmat.primitives",
            "--hidden-import=cryptography.hazmat.primitives.asymmetric",
            "--hidden-import=cryptography.x509",
            "--hidden-import=werkzeug",
            "--hidden-import=werkzeug.serving",
            "--hidden-import=asgiref.sync",
            "--hidden-import=dotenv",
            "--hidden-import=base64",
            "--hidden-import=uuid",
            "--hidden-import=json",
            "--hidden-import=re",
            "--hidden-import=threading",
            "--hidden-import=time",
            "--hidden-import=logging",
            "--hidden-import=mimetypes",
            "--hidden-import=traceback",
            "--hidden-import=shutil",
            "--hidden-import=signal",
            "--hidden-import=atexit",
            "--hidden-import=concurrent",
            "--hidden-import=concurrent.futures",
            "--hidden-import=urllib.parse",
            "--hidden-import=tempfile",
            
            # 排除不必要的模块
            "--exclude-module=tkinter",
            "--exclude-module=test",
            "--exclude-module=unittest",
            "--exclude-module=_curses",
            "--exclude-module=watchdog",
            "--exclude-module=socks",
            "--exclude-module=h2",
            "--exclude-module=brotli",
            "--exclude-module=brotlicffi",
            "--exclude-module=zstandard",
            "--exclude-module=js",
            "--exclude-module=pyodide",
            "--exclude-module=simplejson",
            "--exclude-module=pydoc",
            "--exclude-module=doctest",
            "--exclude-module=pdb",
            "--exclude-module=multiprocessing",
            
            # 添加额外的二进制文件（如果需要）
            "--collect-binaries=mutagen",
            "--collect-binaries=cryptography",
            
            "app_gui.py"
        ]
        
        print("开始构建...")
        print("命令:", " ".join(cmd))
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        
        print("\n构建完成!")
        print("返回码:", result.returncode)
        
        if result.stdout:
            print("\n标准输出:")
            print(result.stdout)
        
        if result.stderr:
            print("\n标准错误:")
            print(result.stderr)
        
        # 检查构建是否成功
        if result.returncode == 0:
            dist_path = os.path.join("dist", "MusicMetadataProcessor.exe")
            if os.path.exists(dist_path):
                print(f"\n✅ 构建成功！可执行文件位置: {dist_path}")
                print(f"文件大小: {os.path.getsize(dist_path) / (1024*1024):.2f} MB")
            else:
                print("\n❌ 构建完成但未找到可执行文件")
                return 1
        else:
            print("\n❌ 构建失败！")
            return result.returncode
        
        return result.returncode
        
    except Exception as e:
        print(f"构建过程中发生错误: {e}")
        traceback.print_exc()
        return 1
        
    finally:
        # 清理临时文件
        try:
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
                print(f"已清理临时目录: {temp_dir}")
        except Exception as e:
            print(f"清理临时文件时出错: {e}")

if __name__ == "__main__":
    sys.exit(build_final())
