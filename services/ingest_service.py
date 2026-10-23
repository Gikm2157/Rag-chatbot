from ingest.policies import process_policy


def ingest_file(file_name: str, s3_url: str, department_id: str = "default"):
    # 可以在这里增加导入前的预处理或校验。
    result = process_policy(file_name, s3_url, department_id=department_id)

    return result


def ingest_uploaded_file(
    file_name: str,
    uploaded_file,
    department_id: str = "default",
) -> dict:
    """将本地上传文件交给同一套 PDF 导入流水线。"""
    return process_policy(
        file_name,
        uploaded_file=uploaded_file,
        department_id=department_id,
    )
