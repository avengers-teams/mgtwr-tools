from __future__ import annotations

from app.core.exceptions import ValidationError


class ResultFileService:
    def __init__(self, repository):
        self.repository = repository

    def load_result_dataset(self, path: str):
        dataset = self.repository.load(path)
        if not dataset.t_columns:
            raise ValidationError("当前结果文件没有 t_ 字段，无法进行显著性分析")
        return dataset

