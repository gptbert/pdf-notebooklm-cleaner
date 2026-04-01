from pdf_notebooklm_cleaner.cli import parse_args


def test_parse_args_basic() -> None:
    args = parse_args(["input.pdf"])
    assert args.input_pdf == "input.pdf"
    assert args.dpi == 200
