#!/usr/bin/env python3
"""
安装 Playwright 浏览器脚本
用于打包前安装必要的浏览器二进制文件
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd):
    """运行命令并输出"""
    print(f"执行: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"错误输出: {result.stderr}")
        raise subprocess.CalledProcessError(result.returncode, cmd)
    else:
        print("执行成功")
        if result.stdout:
            print(f"输出: {result.stdout}")


def main():
    print("=" * 60)
    print("Playwright 浏览器安装工具")
    print("=" * 60)
    print()

    # 设置 Playwright 浏览器安装路径
    browsers_path = Path.home() / ".cache" / "ms-playwright"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)

    print(f"浏览器安装路径: {browsers_path}")
    print()

    try:
        # 检查是否已安装 Playwright
        print("检查 Playwright 是否已安装...")
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "--version"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print("Playwright 未安装，正在安装...")
            run_command([sys.executable, "-m", "pip", "install", "playwright"])
        else:
            print("Playwright 已安装")
            print(f"版本: {result.stdout.strip()}")

        print("\n正在安装浏览器...")

        # 安装 Chromium（推荐用于自动化）
        print("\n1. 安装 Chromium...")
        run_command([sys.executable, "-m", "playwright", "install", "chromium"])

        # 可选：安装其他浏览器
        print("\n2. 安装 Firefox...")
        run_command([sys.executable, "-m", "playwright", "install", "firefox"])

        print("\n3. 安装系统依赖...")
        run_command([sys.executable, "-m", "playwright", "install-deps"])

        print("\n" + "=" * 60)
        print("[成功] Playwright 浏览器安装完成！")
        print("=" * 60)
        print(f"浏览器路径: {browsers_path}")
        print()

        # 验证安装
        print("验证安装...")
        test_script = """
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://www.baidu.com')
        title = await page.title()
        await browser.close()
        return title

title = asyncio.run(test())
print(f"测试成功，页面标题: {title}")
"""

        result = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print("✓ 测试通过")
            print(f"✓ {result.stdout.strip()}")
        else:
            print("✗ 测试失败")
            print(f"错误: {result.stderr}")

    except subprocess.CalledProcessError as e:
        print(f"\n[错误] 安装失败: {e}")
        print("\n可能的解决方案：")
        print("1. 确保网络连接正常")
        print("2. 手动下载浏览器二进制文件")
        print("3. 使用代理设置")
        sys.exit(1)
    except Exception as e:
        print(f"\n[错误] 发生意外错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()