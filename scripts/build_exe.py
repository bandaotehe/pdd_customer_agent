#!/usr/bin/env python3
"""
Agent-Customer 打包脚本
使用 PyInstaller 将项目打包成独立的可执行文件
支持 Windows 平台
"""

import sys
import subprocess
import shutil
import platform
import argparse
from pathlib import Path
import json

def run_command(cmd, cwd=None):
    """运行命令并输出日志"""
    print(f"执行: {' '.join(cmd)}")
    # 在Windows上使用UTF-8编码以避免Unicode字符问题
    encoding = 'utf-8' if platform.system() == 'Windows' else None
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding=encoding)
    if result.returncode != 0:
        print(f"错误: {result.stderr}")
        raise subprocess.CalledProcessError(result.returncode, cmd)
    return result

def check_uv():
    """检查 uv 是否已安装"""
    if shutil.which("uv") is None:
        raise RuntimeError("未检测到 uv，请先安装 uv: pip install uv")

def setup_environment(venv_path, python_version="3.11"):
    """设置 Python 环境"""
    # 检查是否在 Windows 上
    if platform.system() != "Windows":
        print("警告：此脚本主要为 Windows 设计，在其他平台可能需要调整")

    if not venv_path.exists():
        print(f"创建虚拟环境: {venv_path}")
        run_command(["uv", "venv", "--python", python_version])

    print("安装依赖...")
    run_command(["uv", "sync"])

    print("安装 PyInstaller...")
    run_command(["uv", "pip", "install", "pyinstaller"])

def create_temp_directory(dist_path):
    """创建 temp 目录"""
    temp_dir = dist_path / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    print(f"创建临时目录: {temp_dir}")
    return temp_dir

def build_executable(mode="release"):
    """构建可执行文件"""
    # 检查 spec 文件是否存在
    spec_file = Path("scripts/agent_customer.spec")
    if not spec_file.exists():
        raise FileNotFoundError(f"找不到 spec 文件: {spec_file}")

    # 检测 pyinstaller 路径
    # 优先使用虚拟环境中的 pyinstaller，避免 editable install 导致的注册表问题
    venv_pyinstaller = Path(".venv/Scripts/pyinstaller.exe" if platform.system() == "Windows" else ".venv/bin/pyinstaller")
    if venv_pyinstaller.exists():
        pyinstaller_cmd = str(venv_pyinstaller)
    else:
        pyinstaller_cmd = "pyinstaller"

    # 构建命令
    cmd = [
        pyinstaller_cmd,
        "--noconfirm",
        "--distpath", "dist",
        "--workpath", "build",
        str(spec_file)
    ]

    # 注意：当使用 .spec 文件时，优化选项需要在 spec 文件中设置
    print("开始构建...")
    print("正在使用优化的spec配置构建，请耐心等待...")

    try:
        run_command(cmd)
    except subprocess.CalledProcessError as e:
        print(f"构建失败: {e}")
        print("\n可能的解决方案：")
        print("1. 确保所有依赖都已正确安装")
        print("2. 尝试删除 build 和 dist 目录后重新构建")
        print("3. 使用 --mode debug 查看详细错误信息")
        raise

    # 检查构建结果
    dist_path = Path("dist")
    app_dir = dist_path / "AgentCustomer"
    exe_path = app_dir / "AgentCustomer.exe"

    if exe_path.exists():
        file_size = exe_path.stat().st_size / (1024 * 1024)  # MB
        print(f"\n[成功] 构建成功: {exe_path}")
        print(f"文件大小: {file_size:.2f} MB")

        # 创建 temp 目录
        create_temp_directory(app_dir)

        # 创建必要的配置文件
        create_distribution_files(app_dir)

        return exe_path
    else:
        # 列出 dist 目录的内容
        if dist_path.exists():
            print(f"dist 目录内容: {list(dist_path.iterdir())}")
        raise RuntimeError("构建失败，找不到可执行文件")

def create_distribution_files(dist_path):
    """创建分发包需要的额外文件"""
    # 创建 README.txt
    readme_content = """Agent-Customer 电商AI客服助手

运行说明：
1. 双击 AgentCustomer.exe 启动程序
2. 首次运行会自动创建 temp 目录用于存储数据库
3. 配置文件 config.json 可根据需要修改

注意事项：
- 程序需要网络连接才能正常工作
- 建议关闭杀毒软件的实时防护或添加白名单
- 如遇到问题，请查看 dist 目录下的日志文件
- Playwright 浏览器采用外置模式，需要单独安装

配置说明：
- config.json 包含 API 密钥等配置信息
- 请根据实际情况修改相关配置

技术支持：
- 项目地址: https://github.com/your-repo/Agent-Customer
- 问题反馈: 请通过 GitHub Issues 提交
"""

    (dist_path / "README.txt").write_text(readme_content, encoding="utf-8")

    # 创建运行脚本
    if platform.system() == "Windows":
        bat_content = """@echo off
title Agent-Customer 电商AI客服助手
echo 启动 Agent-Customer...
echo.
AgentCustomer.exe
if errorlevel 1 (
    echo.
    echo 程序异常退出，请检查配置文件或联系技术支持
)
pause
"""
        (dist_path / "run.bat").write_text(bat_content, encoding="gbk")

    # 复制必要的配置文件（如果不存在）
    config_src = Path("config.json")
    config_dst = dist_path / "config.json"
    if config_src.exists() and not config_dst.exists():
        shutil.copy2(config_src, config_dst)
        print(f"复制配置文件: {config_dst}")

def create_installer_script(dist_path):
    """创建 NSIS 安装包脚本"""
    nsis_script = f"""
; Agent-Customer 安装包脚本
; 需要 NSIS (https://nsis.sourceforge.io/)

!define APP_NAME "Agent-Customer"
!define APP_VERSION "0.1.0"
!define APP_PUBLISHER "Agent-Customer Team"
!define APP_URL "https://github.com/your-repo/Agent-Customer"
!define APP_EXE "AgentCustomer.exe"

; 包含现代 UI
!include "MUI2.nsh"

; 基本设置
Name "${{APP_NAME}}"
OutFile "${{APP_NAME}}-${{APP_VERSION}}-Setup.exe"
InstallDir "$PROGRAMFILES64\\${{APP_NAME}}"
InstallDirRegKey HKCU "Software\\${{APP_NAME}}" ""
RequestExecutionLevel admin

; 界面设置
!define MUI_ABORTWARNING
!define MUI_ICON "icon\\icon.ico"
!define MUI_UNICON "icon\\icon.ico"

; 安装页面
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; 卸载页面
!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; 语言
!insertmacro MUI_LANGUAGE "SimpChinese"

; 安装组件
Section "主程序" SecMain
    SetOutPath "$INSTDIR"
    File /r "dist\\*"

    ; 创建开始菜单快捷方式
    CreateDirectory "$SMPROGRAMS\\${{APP_NAME}}"
    CreateShortCut "$SMPROGRAMS\\${{APP_NAME}}\\${{APP_NAME}}.lnk" "$INSTDIR\\${{APP_EXE}}"
    CreateShortCut "$SMPROGRAMS\\${{APP_NAME}}\\卸载.lnk" "$INSTDIR\\Uninstall.exe"

    ; 创建桌面快捷方式
    CreateShortCut "$DESKTOP\\${{APP_NAME}}.lnk" "$INSTDIR\\${{APP_EXE}}"

    ; 注册表项
    WriteRegStr HKCU "Software\\${{APP_NAME}}" "" $INSTDIR

    ; 卸载信息
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" "DisplayName" "${{APP_NAME}}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" "UninstallString" "$INSTDIR\\Uninstall.exe"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" "DisplayVersion" "${{APP_VERSION}}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" "Publisher" "${{APP_PUBLISHER}}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" "URLInfoAbout" "${{APP_URL}}"

    WriteUninstaller "$INSTDIR\\Uninstall.exe"
SectionEnd

Section "启动程序" SecRun
    ExecWait "$INSTDIR\\${{APP_EXE}}"
SectionEnd

; 卸载程序
Section "Uninstall"
    Delete "$INSTDIR\\Uninstall.exe"
    RMDir /r "$INSTDIR"

    Delete "$SMPROGRAMS\\${{APP_NAME}}\\*.*"
    RMDir "$SMPROGRAMS\\${{APP_NAME}}"
    Delete "$DESKTOP\\${{APP_NAME}}.lnk"

    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}"
    DeleteRegKey HKCU "Software\\${{APP_NAME}}"
SectionEnd
"""

    nsis_file = Path("installer.nsi")
    nsis_file.write_text(nsis_script, encoding="utf-8")
    print(f"\nNSIS 安装包脚本已创建: {nsis_file}")
    print("请使用 NSIS 编译器生成安装包")

def clean_build():
    """清理构建文件"""
    print("清理构建文件...")
    for dir_name in ["build", "dist"]:
        dir_path = Path(dir_name)
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"删除: {dir_path}")

    # 清理其他可能的临时文件
    for pattern in ["*.pyc", "__pycache__"]:
        for path in Path(".").rglob(pattern):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)

def check_dependencies():
    """检查必要的文件是否存在"""
    required_files = [
        "app.py",
        "config.json",
        "icon/icon.ico",
        "scripts/agent_customer.spec",
        "pyproject.toml",
    ]

    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)

    if missing_files:
        print("错误：缺少必要的文件：")
        for file_path in missing_files:
            print(f"  - {file_path}")
        return False

    return True

def main():
    # 设置控制台输出编码
    if platform.system() == "Windows":
        # 尝试设置控制台编码为 UTF-8
        try:
            import locale
            import ctypes
            # 设置控制台输出编码
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)  # UTF-8
        except (OSError, AttributeError):
            pass

    parser = argparse.ArgumentParser(
        description="构建 Agent-Customer 发布包",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python scripts/build_exe.py                    # 默认构建
  python scripts/build_exe.py --clean            # 清理后构建
  python scripts/build_exe.py --mode debug       # 调试模式
  python scripts/build_exe.py --installer        # 生成安装包脚本
        """
    )

    parser.add_argument(
        "--python",
        default="3.11",
        help="Python 版本，默认 3.11"
    )

    parser.add_argument(
        "--mode",
        choices=["release", "debug"],
        default="release",
        help="构建模式，release(默认) 或 debug"
    )

    parser.add_argument(
        "--clean",
        action="store_true",
        help="先清理构建文件"
    )

    parser.add_argument(
        "--installer",
        action="store_true",
        help="创建 NSIS 安装包脚本"
    )

    parser.add_argument(
        "--check-only",
        action="store_true",
        help="仅检查依赖，不执行构建"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Agent-Customer 打包工具")
    print("=" * 60)

    try:
        # 检查必要的文件
        if not check_dependencies():
            sys.exit(1)

        if args.check_only:
            print("\n[成功] 所有依赖文件都存在，可以开始构建")
            return

        # 检查 uv
        check_uv()

        # 清理
        if args.clean:
            clean_build()
            print()

        # 设置环境
        venv_path = Path(".venv").resolve()
        setup_environment(venv_path, args.python)
        print()

        # 构建
        exe_path = build_executable(args.mode)

        # 创建安装包
        if args.installer:
            create_installer_script(Path("dist"))

        print("\n" + "=" * 60)
        print("[成功] 构建完成！")
        print("=" * 60)
        print(f"可执行文件: {exe_path}")
        print(f"发布目录: {Path('dist').absolute()}")

        if args.installer:
            print(f"安装包脚本: {Path('installer.nsi').absolute()}")

        print("\n运行说明：")
        print("1. 进入 dist/AgentCustomer 目录")
        print("2. 双击 AgentCustomer.exe 或运行 run.bat")

    except KeyboardInterrupt:
        print("\n\n构建被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n[错误] 构建失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()