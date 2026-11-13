"""Item readers: .jsonl, .csv, .txt, labelled files and their errors."""
import json

import pytest

from classify_tool.items import Item, ItemError, items_from_texts, read_items


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_jsonl_ids_and_default_line_number(tmp_path):
    """items.read_items on .jsonl keeps a given id and uses the line number when the id is absent,
    skipping blank lines. Guards the default id rule of the items format.
    """
    p = write(tmp_path / "a.jsonl", '{"id": "x", "text": "one"}\n\n{"text": "three"}\n')
    assert read_items(p) == [Item("x", "one"), Item(3, "three")]


def test_jsonl_labels_and_boolean_label(tmp_path):
    """items.read_items with labeled=True strips a string label and turns a JSON boolean into
    'true'/'false'. Guards normalize_label, which lets yes/no labels be JSON booleans.
    """
    p = write(tmp_path / "a.jsonl", "\n".join(json.dumps(d) for d in [
        {"id": 1, "text": "a", "label": " billing "}, {"id": 2, "text": "b", "label": True}]))
    assert read_items(p, labeled=True) == [Item(1, "a", "billing"), Item(2, "b", "true")]


def test_csv_with_and_without_id(tmp_path):
    """items.read_items on .csv keeps a quoted text with a comma and uses the row number for an
    empty id. Guards the default id of CSV rows.
    """
    p = write(tmp_path / "a.csv", 'id,text\nk1,"hello, world"\n,second\n')
    assert read_items(p) == [Item("k1", "hello, world"), Item(2, "second")]


def test_csv_labeled_needs_label_column(tmp_path):
    """items.read_items refuses a labelled CSV without a label column. Guards the column check
    before any row is read.
    """
    p = write(tmp_path / "a.csv", "id,text\n1,a\n")
    with pytest.raises(ItemError, match="no label column"):
        read_items(p, labeled=True)


def test_txt_one_item_per_line(tmp_path):
    """items.read_items on .txt gives one item per non-blank line with its line number as id. Guards
    the .txt format and its ids.
    """
    p = write(tmp_path / "a.txt", "first\n\n  \nfourth\n")
    assert read_items(p) == [Item(1, "first"), Item(4, "fourth")]


def test_txt_not_for_labels(tmp_path):
    """items.read_items refuses a .txt file for labelled items. Guards the rule that labels need
    .jsonl or .csv.
    """
    with pytest.raises(ItemError, match="must be .jsonl or .csv"):
        read_items(write(tmp_path / "a.txt", "x\n"), labeled=True)


@pytest.mark.parametrize("text, match", [
    ('{"id": 1}\n', "no text"),
    ('{"id": 1, "text": "a"}\n{"id": 1, "text": "b"}\n', "duplicate id 1"),
    ("[1, 2]\n", "not a JSON object"),
    ("{bad\n", "not JSON"),
    ("\n", "no items"),
])
def test_jsonl_errors(tmp_path, text, match):
    """items.read_items refuses a .jsonl line without text, a duplicate id, a non-object, invalid
    JSON and a file without items. Guards each error of the reader, which names the file and
    line.
    """
    with pytest.raises(ItemError, match=match):
        read_items(write(tmp_path / "a.jsonl", text))


def test_missing_label(tmp_path):
    """items.read_items with labeled=True refuses an item without a label, naming file and line.
    Guards the label check of eval inputs.
    """
    with pytest.raises(ItemError, match=r"a.jsonl:1: no label"):
        read_items(write(tmp_path / "a.jsonl", '{"id": 1, "text": "a"}\n'), labeled=True)


def test_unknown_suffix(tmp_path):
    """items.read_items refuses a suffix other than .jsonl, .csv or .txt. Guards the format dispatch
    by suffix.
    """
    with pytest.raises(ItemError, match="must be .jsonl, .csv or .txt"):
        read_items(write(tmp_path / "a.json", "{}"))


def test_item_texts():
    """items.items_from_texts gives --item texts the ids 1..N. Guards the ids of command-line items
    in the output records.
    """
    assert items_from_texts(["a", "b"]) == [Item(1, "a"), Item(2, "b")]


def test_csv_byte_order_mark_keeps_id_column(tmp_path):
    """items.read_items ignores a UTF-8 byte order mark so the first CSV column is still named id.
    Guards the utf-8-sig decoding for CSV files saved by Excel.
    """
    p = tmp_path / "a.csv"
    p.write_bytes("﻿id,text,label\nk1,hello,billing\n".encode("utf-8"))
    assert read_items(p, labeled=True) == [Item("k1", "hello", "billing")]


@pytest.mark.parametrize("id_", [1.5, True, None, [1], {"a": 1}])
def test_jsonl_id_must_be_string_or_integer(tmp_path, id_):
    """items.read_items refuses an id that is a float, boolean, null, list or object. Guards the id
    type check (a boolean is an int in Python and is refused explicitly).
    """
    p = write(tmp_path / "a.jsonl", json.dumps({"id": id_, "text": "a"}) + "\n")
    with pytest.raises(ItemError, match="id must be a string or an integer"):
        read_items(p)
