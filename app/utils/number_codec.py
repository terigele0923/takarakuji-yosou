def encode_numbers(values: list[int]) -> str:
    """番号配列をDB保存用のカンマ区切り文字列へ変換する。"""
    return ",".join(map(str, values))


def decode_numbers(value: str) -> list[int]:
    """DBのカンマ区切り文字列を番号配列へ戻す。空文字列は空配列。"""
    return [int(item) for item in value.split(",")] if value else []
