name: Build Windows Executables

on:
  push:
    tags:
      - 'v*'  # 版本标签触发，如 v1.0.0, v2.1.0
  pull_request:
    branches: [ main, master ]
  workflow_dispatch:  # 允许手动触发

env:
  PYTHON_VERSION: '3.10'  # 根据你的项目需求调整

jobs:
  build-windows:
    strategy:
      matrix:
        arch: [x64, x86]
        include:
          - arch: x64
            python_arch: 'x64'
            artifact_suffix: 'windows-x64'
          - arch: x86
            python_arch: 'x86'
            artifact_suffix: 'windows-x86'

    runs-on: windows-latest
    name: Build Windows ${{ matrix.arch }}

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Python ${{ env.PYTHON_VERSION }} (${{ matrix.python_arch }})
      uses: actions/setup-python@v5
      with:
        python-version: ${{ env.PYTHON_VERSION }}
        architecture: ${{ matrix.python_arch }}

    - name: Display Python version and architecture
      run: |
        python --version
        python -c "import struct; print(f'Python架构: {struct.calcsize(\"P\") * 8}-bit')"

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install wheel setuptools
        # 安装项目依赖（如果有requirements.txt）
        if exist requirements.txt (
          pip install -r requirements.txt
        )
        # 安装构建依赖
        pip install pyinstaller
        # 安装你的应用可能需要的其他依赖
        pip install flask flask_cors mutagen requests PySide6

    - name: Create project icon (if missing)
      run: |
        # 如果图标文件不存在，创建一个简单的占位图标
        if not exist "icon.ico" (
          echo "创建默认图标文件..."
          # 这里可以添加创建默认图标的命令，或者跳过图标使用
          echo "警告: 使用默认图标或跳过图标"
        ) else (
          echo "找到图标文件: icon.ico"
        )

    - name: Run PyInstaller build script
      run: |
        # 修改图标路径为相对路径或项目内的路径
        python build_final.py
        echo "构建完成!"

    - name: Verify executable
      run: |
        if exist "dist\MusicMetadataProcessor.exe" (
          echo "✅ 可执行文件创建成功"
          dir "dist\MusicMetadataProcessor.exe"
          # 检查文件大小
          $file = Get-Item "dist\MusicMetadataProcessor.exe"
          $sizeMB = $file.Length / 1MB
          echo "文件大小: $sizeMB MB"
        ) else (
          echo "❌ 可执行文件未找到"
          Get-ChildItem -Recurse
          exit 1
        )

    - name: Upload artifact
      uses: actions/upload-artifact@v4
      with:
        name: MusicMetadataProcessor-${{ matrix.artifact_suffix }}
        path: dist/MusicMetadataProcessor.exe
        if-no-files-found: error
        retention-days: 7

  # 可选：创建发布版本
  create-release:
    needs: build-windows
    if: startsWith(github.ref, 'refs/tags/')
    runs-on: ubuntu-latest
    name: Create Release

    steps:
    - name: Download all artifacts
      uses: actions/download-artifact@v4
      with:
        path: ./artifacts

    - name: List downloaded artifacts
      run: |
        ls -la ./artifacts/
        find ./artifacts -name "*.exe" -type f

    - name: Create Release
      id: create_release
      uses: actions/create-release@v1
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      with:
        tag_name: ${{ github.ref }}
        release_name: Release ${{ github.ref }}
        draft: false
        prerelease: false
        body: |
          自动构建的 Windows 可执行文件
          包含 x64 和 x86 架构版本

    - name: Upload Windows x64 Release Asset
      uses: actions/upload-release-asset@v1
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      with:
        upload_url: ${{ steps.create_release.outputs.upload_url }}
        asset_path: ./artifacts/MusicMetadataProcessor-windows-x64/MusicMetadataProcessor.exe
        asset_name: MusicMetadataProcessor-${{ github.ref_name }}-windows-x64.exe
        asset_content_type: application/vnd.microsoft.portable-executable

    - name: Upload Windows x86 Release Asset
      uses: actions/upload-release-asset@v1
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      with:
        upload_url: ${{ steps.create_release.outputs.upload_url }}
        asset_path: ./artifacts/MusicMetadataProcessor-windows-x86/MusicMetadataProcessor.exe
        asset_name: MusicMetadataProcessor-${{ github.ref_name }}-windows-x86.exe
        asset_content_type: application/vnd.microsoft.portable-executable

  # 可选：测试构建结果
  test-build:
    needs: build-windows
    runs-on: windows-latest
    name: Test Build Results

    steps:
    - name: Download artifacts
      uses: actions/download-artifact@v4
      with:
        path: ./downloaded-artifacts

    - name: Verify artifacts
      run: |
        echo "下载的artifacts:"
        Get-ChildItem -Recurse ./downloaded-artifacts
        # 检查文件是否存在
        $x64Exists = Test-Path "./downloaded-artifacts/MusicMetadataProcessor-windows-x64/MusicMetadataProcessor.exe"
        $x86Exists = Test-Path "./downloaded-artifacts/MusicMetadataProcessor-windows-x86/MusicMetadataProcessor.exe"
        echo "x64 版本存在: $x64Exists"
        echo "x86 版本存在: $x86Exists"
        if (-not $x64Exists -or -not $x86Exists) {
          exit 1
        }
