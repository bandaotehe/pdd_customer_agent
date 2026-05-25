import sys, subprocess, shutil, platform, os
from pathlib import Path
import argparse

def run(cmd):
    """运行命令"""
    print(f"执行: {' '.join(cmd)}")
    subprocess.check_call(cmd)

def ensure_uv():
    if shutil.which("uv") is None:
        raise RuntimeError("未检测到 uv，请先安装 uv")

def check_platform():
    """检查平台"""
    if platform.system() != "Windows":
        raise RuntimeError(
            "当前平台: " + platform.system() + "\n"
            "Windows exe 构建必须在 Windows 系统上进行！\n"
            "请在 Windows 机器上运行: python scripts/build_win_exe.py"
        )

def main():
    parser = argparse.ArgumentParser(description="构建 Windows 发布包")
    parser.add_argument("--python", default="3.11", help="Python 版本，默认 3.11")
    parser.add_argument("--clean", action="store_true", help="构建前清理")
    args = parser.parse_args()

    check_platform()
    ensure_uv()

    venv_path = Path(".venv").resolve()
    if not venv_path.exists():
        run(["uv", "venv", "--python", args.python])

    run(["uv", "sync"])

    # 安装 PyInstaller（构建依赖）
    run(["uv", "pip", "install", "pyinstaller"])

    # 清理
    if args.clean:
        for d in ["dist", "build"]:
            p = Path(d)
            if p.exists():
                shutil.rmtree(p)
                print(f"已清理: {d}/")

    # 构建命令（通过 uv run 确保使用 venv 中的 pyinstaller）
    cmd = [
        "uv", "run", "pyinstaller",
        "--noconfirm",
        "--distpath", "dist",
        "--workpath", "build",
        "--clean",
        "scripts/agent_customer.spec",
    ]

    run(cmd)

    # 拷贝 Playwright Chromium 浏览器到 dist
    dist_dir = Path("dist") / "AgentCustomer"
    browsers_src = Path.home() / ".cache" / "ms-playwright"
    browsers_dst = dist_dir / "browsers"

    if browsers_src.exists():
        print(f"\n拷贝 Chromium 浏览器到 dist...")
        chromium_dirs = list(browsers_src.glob("chromium-*"))
        if chromium_dirs:
            src = chromium_dirs[0]
            dst = browsers_dst / src.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"  {src.name} -> {dst} (已就绪)")
        else:
            print("  警告: 未找到 Chromium 浏览器，请先运行 playwright install chromium")
    else:
        print("  警告: 未找到 Playwright 浏览器缓存，请先运行 playwright install chromium")

    # 检查结果
    dist_exe = dist_dir / "AgentCustomer.exe"
    if dist_exe.exists():
        total_size = sum(f.stat().st_size for f in dist_dir.rglob("*") if f.is_file()) / (1024 * 1024)
        print(f"\n构建成功: {dist_exe}")
        print(f"输出目录: {dist_dir.absolute()}")
        print(f"总大小: {total_size:.1f} MB")
    else:
        print("构建完成，详见 dist/AgentCustomer/ 目录")

if __name__ == "__main__":
    main()
