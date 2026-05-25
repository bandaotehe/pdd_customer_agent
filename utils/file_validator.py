"""
文件验证器模块
用于验证文件格式和可读性，防止导入错误
"""

import os
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

# 避免导入logger，减少依赖问题


@dataclass
class ValidationResult:
    """验证结果数据类"""
    is_valid: bool
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    suggestions: List[str] = None
    file_info: Dict = None

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []
        if self.file_info is None:
            self.file_info = {}


class FileValidator:
    """文件验证器基类"""

    def validate_basic(self, file_path: str) -> ValidationResult:
        """
        基础文件验证

        Args:
            file_path: 文件路径

        Returns:
            ValidationResult: 验证结果
        """
        path = Path(file_path)

        # 检查文件是否存在
        if not path.exists():
            return ValidationResult(
                is_valid=False,
                error_type="FILE_NOT_FOUND",
                error_message=f"文件不存在: {file_path}",
                suggestions=["检查文件路径是否正确", "确保文件未被删除或移动"],
                file_info={"exists": False}
            )

        # 检查是否为文件
        if not path.is_file():
            return ValidationResult(
                is_valid=False,
                error_type="NOT_A_FILE",
                error_message=f"路径不是文件: {file_path}",
                suggestions=["确保路径指向文件而不是目录"],
                file_info={"is_file": False}
            )

        # 获取文件信息
        file_info = {
            "exists": True,
            "is_file": True,
            "size": path.stat().st_size,
            "extension": path.suffix.lower()
        }

        return ValidationResult(
            is_valid=True,
            file_info=file_info
        )


class ExcelValidator(FileValidator):
    """Excel文件专用验证器"""

    # Excel文件支持的扩展名
    SUPPORTED_EXTENSIONS = {'.xlsx', '.xls'}

    # ZIP文件头魔数（.xlsx本质是ZIP格式）
    ZIP_SIGNATURE = b'PK\x03\x04'

    def validate_basic(self, file_path: str) -> ValidationResult:
        """
        Excel文件基础验证

        Args:
            file_path: 文件路径

        Returns:
            ValidationResult: 验证结果
        """
        # 先进行基础文件验证
        result = super().validate_basic(file_path)
        if not result.is_valid:
            return result

        path = Path(file_path)

        # 检查文件扩展名
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return ValidationResult(
                is_valid=False,
                error_type="UNSUPPORTED_EXTENSION",
                error_message=f"不支持的文件扩展名: {path.suffix}",
                suggestions=[
                    f"支持的Excel格式: {', '.join(self.SUPPORTED_EXTENSIONS)}",
                    "确保文件是有效的Excel文件"
                ],
                file_info=result.file_info
            )

        # 检查文件大小
        if result.file_info["size"] == 0:
            return ValidationResult(
                is_valid=False,
                error_type="EMPTY_FILE",
                error_message="文件为空",
                suggestions=["检查文件是否保存成功", "重新创建或下载文件"],
                file_info=result.file_info
            )

        # 对于.xlsx文件，检查ZIP文件头
        if path.suffix.lower() == '.xlsx':
            try:
                with open(path, 'rb') as f:
                    header = f.read(4)
                    if not header.startswith(self.ZIP_SIGNATURE):
                        return ValidationResult(
                            is_valid=False,
                            error_type="CORRUPTED_FILE",
                            error_message="文件格式错误或已损坏",
                            suggestions=[
                                "重新创建Excel文件",
                                "尝试用Excel打开并另存为",
                                "检查文件是否完整下载"
                            ],
                            file_info=result.file_info
                        )
            except Exception as e:
                return ValidationResult(
                    is_valid=False,
                    error_type="READ_ERROR",
                    error_message=f"读取文件失败: {str(e)}",
                    suggestions=["检查文件是否被其他程序占用", "确保有读取权限"],
                    file_info=result.file_info
                )

        return ValidationResult(
            is_valid=True,
            file_info=result.file_info
        )

    def validate_readable(self, file_path: str) -> ValidationResult:
        """
        验证Excel文件是否可读

        Args:
            file_path: 文件路径

        Returns:
            ValidationResult: 验证结果
        """
        # 先进行基础验证
        basic_result = self.validate_basic(file_path)
        if not basic_result.is_valid:
            return basic_result

        # 额外检查：验证文件确实可以被正确作为二进制文件读取
        # 这可以防止Agno框架尝试用文本方式读取二进制文件
        path = Path(file_path)
        try:
            with open(path, 'rb') as f:
                # 尝试读取一小块内容确保文件可读
                sample = f.read(1024)
                if len(sample) < 10:
                    return ValidationResult(
                        is_valid=False,
                        error_type="FILE_TOO_SMALL",
                        error_message="文件过小，可能不是有效的Excel文件",
                        suggestions=["重新创建或下载Excel文件"],
                        file_info=basic_result.file_info
                    )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                error_type="READ_ERROR",
                error_message=f"无法以二进制模式读取文件: {str(e)}",
                suggestions=["检查文件权限", "确保文件未被其他程序占用"],
                file_info=basic_result.file_info
            )

        try:
            # 尝试导入openpyxl
            import openpyxl
        except ImportError:
            return ValidationResult(
                is_valid=False,
                error_type="MISSING_DEPENDENCY",
                error_message="缺少openpyxl库",
                suggestions=["运行: pip install openpyxl", "确保所有依赖已安装"],
                file_info=basic_result.file_info
            )

        path = Path(file_path)

        try:
            # 尝试用openpyxl加载文件
            workbook = openpyxl.load_workbook(
                filename=str(path),
                data_only=True,
                read_only=True
            )

            # 检查是否有工作表
            if not workbook.worksheets:
                return ValidationResult(
                    is_valid=False,
                    error_type="NO_WORKSHEETS",
                    error_message="Excel文件中没有工作表",
                    suggestions=["添加至少一个工作表", "检查文件是否正确保存"],
                    file_info={**basic_result.file_info, "worksheet_count": 0}
                )

            # 更新文件信息
            file_info = {
                **basic_result.file_info,
                "worksheet_count": len(workbook.worksheets),
                "worksheet_names": [ws.title for ws in workbook.worksheets]
            }

            workbook.close()

            return ValidationResult(
                is_valid=True,
                file_info=file_info
            )

        except Exception as e:
            error_msg = str(e).lower()

            if "bad zip" in error_msg or "zip" in error_msg:
                return ValidationResult(
                    is_valid=False,
                    error_type="CORRUPTED_FILE",
                    error_message="Excel文件已损坏或格式错误",
                    suggestions=[
                        "尝试用Excel修复文件",
                        "重新创建文件",
                        "检查文件是否完整"
                    ],
                    file_info=basic_result.file_info
                )
            elif "permission" in error_msg or "access" in error_msg:
                return ValidationResult(
                    is_valid=False,
                    error_type="PERMISSION_DENIED",
                    error_message="没有文件访问权限",
                    suggestions=[
                        "关闭文件正在使用的程序",
                        "检查文件权限设置",
                        "以管理员身份运行"
                    ],
                    file_info=basic_result.file_info
                )
            else:
                return ValidationResult(
                    is_valid=False,
                    error_type="READ_ERROR",
                    error_message=f"读取Excel文件失败: {str(e)}",
                    suggestions=[
                        "检查文件是否为有效的Excel文件",
                        "尝试用Excel打开文件验证",
                        "确保文件版本兼容"
                    ],
                    file_info=basic_result.file_info
                )