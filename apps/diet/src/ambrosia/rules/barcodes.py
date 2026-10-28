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
    """GS1's check: the last digit is the check digit of the ones before it."""
    return checkDigit(digits[:-1]) == digits[-1]


def checkDigit(body: str) -> str:
    """GS1's check digit for the digits before it: from the right they're weighted 3, 1, 3, …, and the check digit
    makes the sum a multiple of 10."""
    weighted = sum(int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(body)))
    return str((10 - weighted % 10) % 10)


def weighedPack(barcode: str) -> tuple[str, float] | None:
    """A Finnish weighed pack (GS1 Finland, AM11.1): EAN-13 as 23 YYYY AA PPPP and the check digit, where the item
    is 23 YYYY AA and PPPP its weight, in grams after 23 (under 10 kg), tens of grams after 24 and hundreds after 25.
    Returns the item's code with the weight as 0000, the way GS1 Finland registers it, so every pack of it finds the
    same food, and the pack's grams. None for any other barcode."""
    if len(barcode) != 13 or barcode[:2] not in ("23", "24", "25"):
        return None
    item = barcode[:8] + "0000"
    grams = int(barcode[8:12]) * {"23": 1, "24": 10, "25": 100}[barcode[:2]]
    return item + checkDigit(item), float(grams)


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
