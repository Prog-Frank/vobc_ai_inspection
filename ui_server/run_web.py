"""启动入口 - 包含许可证验证"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# from license import LicenseManager


def main():
    # 开发模式：跳过许可证验证
    # lic_manager = LicenseManager(os.path.join(os.path.dirname(__file__), '..', 'license.lic'))
    # result = lic_manager.verify()
    # if not result['valid']:
    #     print(f"错误: {result['message']}")
    #     print("请联系管理员获取有效的许可证文件")
    #     sys.exit(1)
    # print(f"许可证验证通过: {result['message']}")

    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8002, reload=True)


if __name__ == "__main__":
    main()