from app.utils.number_codec import decode_numbers, encode_numbers


def test_番号配列とDB文字列を相互変換する():
    assert encode_numbers([1, 5, 12]) == "1,5,12"
    assert decode_numbers("1,5,12") == [1, 5, 12]
    assert encode_numbers([]) == ""
    assert decode_numbers("") == []
