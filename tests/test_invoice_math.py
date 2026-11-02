from services.invoice_math import check_invoice_math


def _invoice(**overrides):
    data = {
        "line_items": [
            {"description": "12 AWG THHN wire, 500 ft spool", "quantity": "12", "unit_price": "144.20", "total": "1730.40"},
            {"description": '3/4" EMT conduit, 10 ft', "quantity": "200", "unit_price": "9.55", "total": "1910.00"},
            {"description": "200A panelboard", "quantity": "1", "unit_price": "1498.00", "total": "1498.00"},
        ],
        "subtotal": "5138.40",
        "tax_amount": "423.92",
        "total_amount": "5562.32",
    }
    data.update(overrides)
    return data


def test_consistent_invoice_has_no_issues() -> None:
    assert check_invoice_math(_invoice()) == []


def test_misread_total_is_flagged_with_both_amounts() -> None:
    issues = check_invoice_math(_invoice(total_amount="5532.32"))

    assert issues == [
        "Totals don't add up: line items come to $5,562.32 (including $423.92 tax), "
        "invoice says $5,532.32"
    ]


def test_one_cent_rounding_difference_is_tolerated() -> None:
    assert check_invoice_math(_invoice(total_amount="5562.33")) == []
    assert check_invoice_math(_invoice(total_amount="5562.31")) == []


def test_two_cent_difference_is_flagged() -> None:
    assert len(check_invoice_math(_invoice(total_amount="5562.34"))) == 1


def test_line_where_quantity_times_price_differs_is_flagged() -> None:
    data = _invoice()
    data["line_items"][1]["total"] = "1190.00"
    data["total_amount"] = "4842.32"  # keeps the invoice total consistent with the bad line

    issues = check_invoice_math(data)

    assert issues == [
        "Line 2 doesn't add up: 200 x $9.55 = $1,910.00, but the line says $1,190.00"
    ]


def test_freight_is_included_when_present() -> None:
    assert check_invoice_math(_invoice(freight_amount="75.00", total_amount="5637.32")) == []
    issues = check_invoice_math(_invoice(freight_amount="75.00"))
    assert "including $423.92 tax and $75.00 freight" in issues[0]


def test_missing_tax_counts_as_zero() -> None:
    assert check_invoice_math(_invoice(tax_amount=None, total_amount="5138.40")) == []


def test_totals_check_skipped_when_a_line_amount_is_missing() -> None:
    data = _invoice(total_amount="1.00")
    data["line_items"][2]["total"] = None

    assert check_invoice_math(data) == []


def test_no_line_items_or_total_means_nothing_to_check() -> None:
    assert check_invoice_math({"total_amount": "100.00", "line_items": []}) == []
    assert check_invoice_math(_invoice(total_amount=None)) == []


def test_formatted_strings_and_numbers_are_parsed() -> None:
    data = _invoice(total_amount="$5,562.32", tax_amount=423.92)
    assert check_invoice_math(data) == []
