import gzip

from server import decode_csv_upload


def test_decode_csv_upload() -> None:
    csv = b"sec,CH1\n0,1\n"
    assert decode_csv_upload(csv, "signal.csv") == csv
    assert decode_csv_upload(gzip.compress(csv), "signal.csv.gz") == csv


if __name__ == "__main__":
    test_decode_csv_upload()
