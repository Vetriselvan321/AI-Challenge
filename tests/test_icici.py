import pandas as pd
from custom_parsers.icici_parser import parse

def test_parser():
    df = parse(r"data\icici\icici_sample.pdf")
    expected = pd.read_csv(r"data\icici\icici_expected.csv")
    assert df.astype(str).equals(expected.astype(str))