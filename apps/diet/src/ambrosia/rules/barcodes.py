"""Food barcodes (apps/diet/docs/plan.md 4d, AM5.4): EAN-13, EAN-8, UPC-A and GTIN-14, checked by their last
digit so a typing mistake isn't looked up, and the shops' own codes, which Ambrosia looks up only in your
foods because each shop gives them to its own items (Open Food Facts matched one to another shop's cheese).
"""

shopCodeHint = "A shop's own code: looked up only in your foods."


def cleanBarcode(text: str) -> str:
    """The barcode typed or scanned, as digits. Raises ValueError, in plain words, if it can't be one."""
    digits = "".join(text.split())
    if not digits.isdigit():
        raise ValueError("A barcode has only digits.")
    if len(digits) not in (8, 12, 13, 14):
        raise ValueError("A food barcode has 8, 12, 13 or 14 digits.")
    if not checkDigitFits(digits):
        raise ValueError("That barcode's last digit doesn't fit the others: check it against the pack.")
    return digits


def checkDigitFits(digits: str) -> bool:
    """GS1's check: from the right, the digits before the last are weighted 3, 1, 3, …. The last digit makes the
    sum a multiple of 10."""
    body, last = digits[:-1], int(digits[-1])
    weighted = sum(int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(body)))
    return (10 - weighted % 10) % 10 == last


def isShopCode(barcode: str) -> bool:
    """GS1's ranges for codes a shop gives its own items (often weighed at the counter): EAN-13 starting with 2,
    or 02 or 04 (UPC-A's own ranges written as EAN-13). UPC-A starting with 2 or 4. EAN-8 starting with 0 or 2."""
    if len(barcode) == 13:
        return barcode[0] == "2" or barcode[:2] in ("02", "04")
    if len(barcode) == 12:
        return barcode[0] in "24"
    if len(barcode) == 8:
        return barcode[0] in "02"
    return False
