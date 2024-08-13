from __future__ import annotations

import copy
import math
import os
import re
import string
import sys
import tempfile
from collections import Counter
from curses import ascii
from io import BytesIO
from pathlib import Path
from typing import Any, Generator, IO
import fsutil
import ots
from fontTools import unicodedata
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.subset import Options as SubsetterOptions
from fontTools.subset import Subsetter
from fontTools.ttLib import TTCollection, TTFont, TTLibError
from fontTools.varLib import instancer
from fontTools.varLib.instancer import OverlapMode
from PIL import Image, ImageDraw, ImageFont

from fontbro.exceptions import (
    ArgumentError,
    DataError,
    OperationError,
    SanitizationError,
)
from fontbro.flags import get_flag, set_flag
from fontbro.math import get_euclidean_distance
from fontbro.subset import parse_unicodes
from fontbro.utils import (
    concat_names,
    find_item,
    read_json,
    remove_spaces,
    slugify,
)


class Font:
    """
    friendly font operations on top of fontTools.
    """

    # Family Classification:
    # https://learn.microsoft.com/en-us/typography/opentype/spec/ibmfc
    _FAMILY_CLASSIFICATIONS: dict[str, list[dict[str, Any]]] = read_json(
        "data/family-classifications.json"
    )
    # fmt: off
    FAMILY_CLASSIFICATION_NO_CLASSIFICATION: dict[str, int] = {'class_id': 0}
    FAMILY_CLASSIFICATION_OLDSTYLE_SERIFS: dict[str, int] = {'class_id': 1}
    FAMILY_CLASSIFICATION_OLDSTYLE_SERIFS_NO_CLASSIFICATION: dict[str, int] = {'class_id':1, 'subclass_id':0}
    FAMILY_CLASSIFICATION_OLDSTYLE_SERIFS_IBM_ROUNDED_LEGIBILITY: dict[str, int] = {'class_id':1, 'subclass_id':1}
    FAMILY_CLASSIFICATION_OLDSTYLE_SERIFS_GARALDE: dict[str, int] = {'class_id':1, 'subclass_id':2}
    FAMILY_CLASSIFICATION_OLDSTYLE_SERIFS_VENETIAN: dict[str, int] = {'class_id':1, 'subclass_id':3}
    FAMILY_CLASSIFICATION_OLDSTYLE_SERIFS_MODIFIED_VENETIAN: dict[str, int] = {'class_id':1, 'subclass_id':4}
    FAMILY_CLASSIFICATION_OLDSTYLE_SERIFS_DUTCH_MODERN: dict[str, int] = {'class_id':1, 'subclass_id':5}
    FAMILY_CLASSIFICATION_OLDSTYLE_SERIFS_DUTCH_TRADITIONAL: dict[str, int] = {'class_id':1, 'subclass_id':6}
    FAMILY_CLASSIFICATION_OLDSTYLE_SERIFS_CONTEMPORARY: dict[str, int] = {'class_id':1, 'subclass_id':7}
    FAMILY_CLASSIFICATION_OLDSTYLE_SERIFS_CALLIGRAPHIC: dict[str, int] = {'class_id':1, 'subclass_id':8}
    FAMILY_CLASSIFICATION_OLDSTYLE_SERIFS_MISCELLANEOUS: dict[str, int] = {'class_id':1, 'subclass_id':15}
    FAMILY_CLASSIFICATION_TRANSITIONAL_SERIFS: dict[str, int] = {'class_id': 2}
    FAMILY_CLASSIFICATION_TRANSITIONAL_SERIFS_NO_CLASSIFICATION: dict[str, int] = {'class_id':2, 'subclass_id':0}
    FAMILY_CLASSIFICATION_TRANSITIONAL_SERIFS_DIRECT_LINE: dict[str, int] = {'class_id':2, 'subclass_id':1}
    FAMILY_CLASSIFICATION_TRANSITIONAL_SERIFS_SCRIPT: dict[str, int] = {'class_id':2, 'subclass_id':2}
    FAMILY_CLASSIFICATION_TRANSITIONAL_SERIFS_MISCELLANEOUS: dict[str, int] = {'class_id':2, 'subclass_id':15}
    FAMILY_CLASSIFICATION_MODERN_SERIFS: dict[str, int] = {'class_id': 3}
    FAMILY_CLASSIFICATION_MODERN_SERIFS_NO_CLASSIFICATION: dict[str, int] = {'class_id':3, 'subclass_id':0}
    FAMILY_CLASSIFICATION_MODERN_SERIFS_ITALIAN: dict[str, int] = {'class_id':3, 'subclass_id':1}
    FAMILY_CLASSIFICATION_MODERN_SERIFS_SCRIPT: dict[str, int] = {'class_id':3, 'subclass_id':2}
    FAMILY_CLASSIFICATION_MODERN_SERIFS_MISCELLANEOUS: dict[str, int] = {'class_id':3, 'subclass_id':15}
    FAMILY_CLASSIFICATION_CLARENDON_SERIFS: dict[str, int] = {'class_id': 4}
    FAMILY_CLASSIFICATION_CLARENDON_SERIFS_NO_CLASSIFICATION: dict[str, int] = {'class_id':4, 'subclass_id':0}
    FAMILY_CLASSIFICATION_CLARENDON_SERIFS_CLARENDON: dict[str, int] = {'class_id':4, 'subclass_id':1}
    FAMILY_CLASSIFICATION_CLARENDON_SERIFS_MODERN: dict[str, int] = {'class_id':4, 'subclass_id':2}
    FAMILY_CLASSIFICATION_CLARENDON_SERIFS_TRADITIONAL: dict[str, int] = {'class_id':4, 'subclass_id':3}
    FAMILY_CLASSIFICATION_CLARENDON_SERIFS_NEWSPAPER: dict[str, int] = {'class_id':4, 'subclass_id':4}
    FAMILY_CLASSIFICATION_CLARENDON_SERIFS_STUB_SERIF: dict[str, int] = {'class_id':4, 'subclass_id':5}
    FAMILY_CLASSIFICATION_CLARENDON_SERIFS_MONOTONE: dict[str, int] = {'class_id':4, 'subclass_id':6}
    FAMILY_CLASSIFICATION_CLARENDON_SERIFS_TYPEWRITER: dict[str, int] = {'class_id':4, 'subclass_id':7}
    FAMILY_CLASSIFICATION_CLARENDON_SERIFS_MISCELLANEOUS: dict[str, int] = {'class_id':4, 'subclass_id':15}
    FAMILY_CLASSIFICATION_SLAB_SERIFS: dict[str, int] = {'class_id': 5}
    FAMILY_CLASSIFICATION_SLAB_SERIFS_NO_CLASSIFICATION: dict[str, int] = {'class_id':5, 'subclass_id':0}
    FAMILY_CLASSIFICATION_SLAB_SERIFS_MONOTONE: dict[str, int] = {'class_id':5, 'subclass_id':1}
    FAMILY_CLASSIFICATION_SLAB_SERIFS_HUMANIST: dict[str, int] = {'class_id':5, 'subclass_id':2}
    FAMILY_CLASSIFICATION_SLAB_SERIFS_GEOMETRIC: dict[str, int] = {'class_id':5, 'subclass_id':3}
    FAMILY_CLASSIFICATION_SLAB_SERIFS_SWISS: dict[str, int] = {'class_id':5, 'subclass_id':4}
    FAMILY_CLASSIFICATION_SLAB_SERIFS_TYPEWRITER: dict[str, int] = {'class_id':5, 'subclass_id':5}
    FAMILY_CLASSIFICATION_SLAB_SERIFS_MISCELLANEOUS: dict[str, int] = {'class_id':5, 'subclass_id':15}
    FAMILY_CLASSIFICATION_FREEFORM_SERIFS: dict[str, int] = {'class_id': 7}
    FAMILY_CLASSIFICATION_FREEFORM_SERIFS_NO_CLASSIFICATION: dict[str, int] = {'class_id':7, 'subclass_id':0}
    FAMILY_CLASSIFICATION_FREEFORM_SERIFS_MODERN: dict[str, int] = {'class_id':7, 'subclass_id':1}
    FAMILY_CLASSIFICATION_FREEFORM_SERIFS_MISCELLANEOUS: dict[str, int] = {'class_id':7, 'subclass_id':15}
    FAMILY_CLASSIFICATION_SANS_SERIF: dict[str, int] = {'class_id': 8}
    FAMILY_CLASSIFICATION_SANS_SERIF_NO_CLASSIFICATION: dict[str, int] = {'class_id':8, 'subclass_id':0}
    FAMILY_CLASSIFICATION_SANS_SERIF_IBM_NEO_GROTESQUE_GOTHIC: dict[str, int] = {'class_id':8, 'subclass_id':1}
    FAMILY_CLASSIFICATION_SANS_SERIF_HUMANIST: dict[str, int] = {'class_id':8, 'subclass_id':2}
    FAMILY_CLASSIFICATION_SANS_SERIF_LOW_X_ROUND_GEOMETRIC: dict[str, int] = {'class_id':8, 'subclass_id':3}
    FAMILY_CLASSIFICATION_SANS_SERIF_HIGH_X_ROUND_GEOMETRIC: dict[str, int] = {'class_id':8, 'subclass_id':4}
    FAMILY_CLASSIFICATION_SANS_SERIF_NEO_GROTESQUE_GOTHIC: dict[str, int] = {'class_id':8, 'subclass_id':5}
    FAMILY_CLASSIFICATION_SANS_SERIF_MODIFIED_NEO_GROTESQUE_GOTHIC: dict[str, int] = {'class_id':8, 'subclass_id':6}
    FAMILY_CLASSIFICATION_SANS_SERIF_TYPEWRITER_GOTHIC: dict[str, int] = {'class_id':8, 'subclass_id':9}
    FAMILY_CLASSIFICATION_SANS_SERIF_MATRIX: dict[str, int] = {'class_id':8, 'subclass_id':10}
    FAMILY_CLASSIFICATION_SANS_SERIF_MISCELLANEOUS: dict[str, int] = {'class_id':8, 'subclass_id':15}
    FAMILY_CLASSIFICATION_ORNAMENTALS: dict[str, int] = {'class_id': 9}
    FAMILY_CLASSIFICATION_ORNAMENTALS_NO_CLASSIFICATION: dict[str, int] = {'class_id':9, 'subclass_id':0}
    FAMILY_CLASSIFICATION_ORNAMENTALS_ENGRAVER: dict[str, int] = {'class_id':9, 'subclass_id':1}
    FAMILY_CLASSIFICATION_ORNAMENTALS_BLACK_LETTER: dict[str, int] = {'class_id':9, 'subclass_id':2}
    FAMILY_CLASSIFICATION_ORNAMENTALS_DECORATIVE: dict[str, int] = {'class_id':9, 'subclass_id':3}
    FAMILY_CLASSIFICATION_ORNAMENTALS_THREE_DIMENSIONAL: dict[str, int] = {'class_id':9, 'subclass_id':4}
    FAMILY_CLASSIFICATION_ORNAMENTALS_MISCELLANEOUS: dict[str, int] = {'class_id':9, 'subclass_id':15}
    FAMILY_CLASSIFICATION_SCRIPTS: dict[str, int] = {'class_id': 10}
    FAMILY_CLASSIFICATION_SCRIPTS_NO_CLASSIFICATION: dict[str, int] = {'class_id':10, 'subclass_id':0}
    FAMILY_CLASSIFICATION_SCRIPTS_UNCIAL: dict[str, int] = {'class_id':10, 'subclass_id':1}
    FAMILY_CLASSIFICATION_SCRIPTS_BRUSH_JOINED: dict[str, int] = {'class_id':10, 'subclass_id':2}
    FAMILY_CLASSIFICATION_SCRIPTS_FORMAL_JOINED: dict[str, int] = {'class_id':10, 'subclass_id':3}
    FAMILY_CLASSIFICATION_SCRIPTS_MONOTONE_JOINED: dict[str, int] = {'class_id':10, 'subclass_id':4}
    FAMILY_CLASSIFICATION_SCRIPTS_CALLIGRAPHIC: dict[str, int] = {'class_id':10, 'subclass_id':5}
    FAMILY_CLASSIFICATION_SCRIPTS_BRUSH_UNJOINED: dict[str, int] = {'class_id':10, 'subclass_id':6}
    FAMILY_CLASSIFICATION_SCRIPTS_FORMAL_UNJOINED: dict[str, int] = {'class_id':10, 'subclass_id':7}
    FAMILY_CLASSIFICATION_SCRIPTS_MONOTONE_UNJOINED: dict[str, int] = {'class_id':10, 'subclass_id':8}
    FAMILY_CLASSIFICATION_SCRIPTS_MISCELLANEOUS: dict[str, int] = {'class_id':10, 'subclass_id':15}
    FAMILY_CLASSIFICATION_SYMBOLIC: dict[str, int] = {'class_id': 12}
    FAMILY_CLASSIFICATION_SYMBOLIC_NO_CLASSIFICATION: dict[str, int] = {'class_id':12, 'subclass_id':0}
    FAMILY_CLASSIFICATION_SYMBOLIC_MIXED_SERIF: dict[str, int] = {'class_id':12, 'subclass_id':3}
    FAMILY_CLASSIFICATION_SYMBOLIC_OLDSTYLE_SERIF: dict[str, int] = {'class_id':12, 'subclass_id':6}
    FAMILY_CLASSIFICATION_SYMBOLIC_NEO_GROTESQUE_SANS_SERIF: dict[str, int] = {'class_id':12, 'subclass_id':7}
    FAMILY_CLASSIFICATION_SYMBOLIC_MISCELLANEOUS: dict[str, int] = {'class_id':12, 'subclass_id':15}
    # fmt: on

    # Features:
    # https://docs.microsoft.com/en-gb/typography/opentype/spec/featurelist
    # https://developer.mozilla.org/en-US/docs/Web/CSS/font-feature-settings
    _FEATURES_LIST: list[dict[str, Any]] = read_json("data/features.json")
    _FEATURES_BY_TAG: dict[str, dict[str, Any]] = {
        feature["tag"]: feature for feature in _FEATURES_LIST
    }

    # Formats:
    FORMAT_OTF: str = "otf"
    FORMAT_TTF: str = "ttf"
    FORMAT_WOFF: str = "woff"
    FORMAT_WOFF2: str = "woff2"

    _FORMATS_LIST: list[str] = [FORMAT_OTF, FORMAT_TTF, FORMAT_WOFF, FORMAT_WOFF2]

    # Names:
    NAME_COPYRIGHT_NOTICE: str = "copyright_notice"
    NAME_FAMILY_NAME: str = "family_name"
    NAME_SUBFAMILY_NAME: str = "subfamily_name"
    NAME_UNIQUE_IDENTIFIER: str = "unique_identifier"
    NAME_FULL_NAME: str = "full_name"
    NAME_VERSION: str = "version"
    NAME_POSTSCRIPT_NAME: str = "postscript_name"
    NAME_TRADEMARK: str = "trademark"
    NAME_MANUFACTURER_NAME: str = "manufacturer_name"
    NAME_DESIGNER: str = "designer"
    NAME_DESCRIPTION: str = "description"
    NAME_VENDOR_URL: str = "vendor_url"
    NAME_DESIGNER_URL: str = "designer_url"
    NAME_LICENSE_DESCRIPTION: str = "license_description"
    NAME_LICENSE_INFO_URL: str = "license_info_url"
    NAME_RESERVED: str = "reserved"
    NAME_TYPOGRAPHIC_FAMILY_NAME: str = "typographic_family_name"
    NAME_TYPOGRAPHIC_SUBFAMILY_NAME: str = "typographic_subfamily_name"
    NAME_COMPATIBLE_FULL: str = "compatible_full"
    NAME_SAMPLE_TEXT: str = "sample_text"
    NAME_POSTSCRIPT_CID_FINDFONT_NAME: str = "postscript_cid_findfont_name"
    NAME_WWS_FAMILY_NAME: str = "wws_family_name"
    NAME_WWS_SUBFAMILY_NAME: str = "wws_subfamily_name"
    NAME_LIGHT_BACKGROUND_PALETTE: str = "light_background_palette"
    NAME_DARK_BACKGROUND_PALETTE: str = "dark_background_palette"
    NAME_VARIATIONS_POSTSCRIPT_NAME_PREFIX: str = "variations_postscript_name_prefix"

    _NAMES: list[dict[str, Any]] = [
        {"id": 0, "key": NAME_COPYRIGHT_NOTICE},
        {"id": 1, "key": NAME_FAMILY_NAME},
        {"id": 2, "key": NAME_SUBFAMILY_NAME},
        {"id": 3, "key": NAME_UNIQUE_IDENTIFIER},
        {"id": 4, "key": NAME_FULL_NAME},
        {"id": 5, "key": NAME_VERSION},
        {"id": 6, "key": NAME_POSTSCRIPT_NAME},
        {"id": 7, "key": NAME_TRADEMARK},
        {"id": 8, "key": NAME_MANUFACTURER_NAME},
        {"id": 9, "key": NAME_DESIGNER},
        {"id": 10, "key": NAME_DESCRIPTION},
        {"id": 11, "key": NAME_VENDOR_URL},
        {"id": 12, "key": NAME_DESIGNER_URL},
        {"id": 13, "key": NAME_LICENSE_DESCRIPTION},
        {"id": 14, "key": NAME_LICENSE_INFO_URL},
        {"id": 15, "key": NAME_RESERVED},
        {"id": 16, "key": NAME_TYPOGRAPHIC_FAMILY_NAME},
        {"id": 17, "key": NAME_TYPOGRAPHIC_SUBFAMILY_NAME},
        {"id": 18, "key": NAME_COMPATIBLE_FULL},
        {"id": 19, "key": NAME_SAMPLE_TEXT},
        {"id": 20, "key": NAME_POSTSCRIPT_CID_FINDFONT_NAME},
        {"id": 21, "key": NAME_WWS_FAMILY_NAME},
        {"id": 22, "key": NAME_WWS_SUBFAMILY_NAME},
        {"id": 23, "key": NAME_LIGHT_BACKGROUND_PALETTE},
        {"id": 24, "key": NAME_DARK_BACKGROUND_PALETTE},
        {"id": 25, "key": NAME_VARIATIONS_POSTSCRIPT_NAME_PREFIX},
    ]
    _NAMES_BY_ID: dict[int, dict[str, Any]] = {item["id"]: item for item in _NAMES}
    _NAMES_BY_KEY: dict[str, dict[str, Any]] = {item["key"]: item for item in _NAMES}
    _NAMES_MAC_IDS: dict[str, Any] = {"platformID": 3, "platEncID": 1, "langID": 0x409}
    _NAMES_WIN_IDS: dict[str, Any] = {"platformID": 1, "platEncID": 0, "langID": 0x0}

    _NAME_TABLE_LOOKUP = {
        0: {
            "name": "Unicode",
            "encoding": {
                0: "Unicode 1.0 semantics",
                1: "Unicode 1.1 semantics",
                2: "ISO/IEC 10646 semantics",
                3: "Unicode 2.0 and onwards semantics, Unicode BMP only",
                4: "Unicode 2.0 and onwards semantics, Unicode full repertoire",
            },
            "language": {},
        },
        1: {
            "name": "Macintosh",
            "encoding": {
                0: "Roman",
                1: "Japanese",
                2: "Traditional Chinese",
                3: "Korean",
                4: "Arabic",
                5: "Hebrew",
                6: "Greek",
                7: "Russian",
                8: "RSymbol",
                9: "Devanagari",
                10: "Gurmukhi",
                11: "Gujarati",
                12: "Oriya",
                13: "Bengali",
                14: "Tamil",
                15: "Telugu",
                16: "Kannada",
                17: "Malayalam",
                18: "Sinhalese",
                19: "Burmese",
                20: "Khmer",
                21: "Thai",
                22: "Laotian",
                23: "Georgian",
                24: "Armenian",
                25: "Simplified Chinese",
                26: "Tibetan",
                27: "Mongolian",
                28: "Geez",
                29: "Slavic",
                30: "Vietnamese",
                31: "Sindhi",
                32: "Uninterpreted",
            },
            "language": {
                0: "English",
                1: "French",
                2: "German",
                3: "Italian",
                4: "Dutch",
                5: "Swedish",
                6: "Spanish",
                7: "Danish",
                8: "Portuguese",
                9: "Norwegian",
                10: "Hebrew",
                11: "Japanese",
                12: "Arabic",
                13: "Finnish",
                14: "Greek",
                15: "Icelandic",
                16: "Maltese",
                17: "Turkish",
                18: "Croatian",
                19: "Chinese (traditional)",
                20: "Urdu",
                21: "Hindi",
                22: "Thai",
                23: "Korean",
                24: "Lithuanian",
                25: "Polish",
                26: "Hungarian",
                27: "Estonian",
                28: "Latvian",
                29: "Sami",
                30: "Faroese",
                31: "Farsi/Persian",
                32: "Russian",
                33: "Chinese (simplified)",
                34: "Flemish",
                35: "Irish Gaelic",
                36: "Albanian",
                37: "Romanian",
                38: "Czech",
                39: "Slovak",
                40: "Slovenian",
                41: "Yiddish",
                42: "Serbian",
                43: "Macedonian",
                44: "Bulgarian",
                45: "Ukrainian",
                46: "Byelorussian",
                47: "Uzbek",
                48: "Kazakh",
                49: "Azerbaijani (Cyrillic script)",
                50: "Azerbaijani (Arabic script)",
                51: "Armenian",
                52: "Georgian",
                53: "Moldavian",
                54: "Kirghiz",
                55: "Tajiki",
                56: "Turkmen",
                57: "Mongolian (Mongolian script)",
                58: "Mongolian (Cyrillic script)",
                59: "Pashto",
                60: "Kurdish",
                61: "Kashmiri",
                62: "Sindhi",
                63: "Tibetan",
                64: "Nepali",
                65: "Sanskrit",
                66: "Marathi",
                67: "Bengali",
                68: "Assamese",
                69: "Gujarati",
                70: "Punjabi",
                71: "Oriya",
                72: "Malayalam",
                73: "Kannada",
                74: "Tamil",
                75: "Telugu",
                76: "Sinhalese",
                77: "Burmese",
                78: "Khmer",
                79: "Lao",
                80: "Vietnamese",
                81: "Indonesian",
                82: "Tagalog",
                83: "Malay (Roman script)",
                84: "Malay (Arabic script)",
                85: "Amharic",
                86: "Tigrinya",
                87: "Galla",
                88: "Somali",
                89: "Swahili",
                90: "Kinyarwanda/Ruanda",
                91: "Rundi",
                92: "Nyanja/Chewa",
                93: "Malagasy",
                94: "Esperanto",
                128: "Welsh",
                129: "Basque",
                130: "Catalan",
                131: "Latin",
                132: "Quechua",
                133: "Guarani",
                134: "Aymara",
                135: "Tatar",
                136: "Uighur",
                137: "Dzongkha",
                138: "Javanese (Roman script)",
                139: "Sundanese (Roman script)",
                140: "Galician",
                141: "Afrikaans",
                142: "Breton",
                143: "Inuktitut",
                144: "Scottish Gaelic",
                145: "Manx Gaelic",
                146: "Irish Gaelic (with dot above)",
                147: "Tongan",
                148: "Greek (polytonic)",
                149: "Greenlandic",
                150: "Azerbaijani (Roman script)",
            },
        },
        3: {
            "name": "Windows",
            "encoding": {
                0: "Symbol",
                1: "Unicode BMP",
                2: "ShiftJIS",
                3: "PRC",
                4: "Big5",
                5: "Wansung",
                6: "Johab",
                10: "Unicode UCS-4",
            },
            "language": {
                0x0001: "ar",
                0x0002: "bg",
                0x0003: "ca",
                0x0004: "zh-Hans",
                0x0005: "cs",
                0x0006: "da",
                0x0007: "de",
                0x0008: "el",
                0x0009: "en",
                0x000A: "es",
                0x000B: "fi",
                0x000C: "fr",
                0x000D: "he",
                0x000E: "hu",
                0x000F: "is",
                0x0010: "it",
                0x0011: "ja",
                0x0012: "ko",
                0x0013: "nl",
                0x0014: "no",
                0x0015: "pl",
                0x0016: "pt",
                0x0017: "rm",
                0x0018: "ro",
                0x0019: "ru",
                0x001A: "hr",
                0x001B: "sk",
                0x001C: "sq",
                0x001D: "sv",
                0x001E: "th",
                0x001F: "tr",
                0x0020: "ur",
                0x0021: "id",
                0x0022: "uk",
                0x0023: "be",
                0x0024: "sl",
                0x0025: "et",
                0x0026: "lv",
                0x0027: "lt",
                0x0028: "tg",
                0x0029: "fa",
                0x002A: "vi",
                0x002B: "hy",
                0x002C: "az",
                0x002D: "eu",
                0x002E: "hsb",
                0x002F: "mk",
                0x0030: "st",
                0x0031: "ts",
                0x0032: "tn",
                0x0033: "ve",
                0x0034: "xh",
                0x0035: "zu",
                0x0036: "af",
                0x0037: "ka",
                0x0038: "fo",
                0x0039: "hi",
                0x003A: "mt",
                0x003B: "se",
                0x003C: "ga",
                0x003D: "yi",
                0x003E: "ms",
                0x003F: "kk",
                0x0040: "ky",
                0x0041: "sw",
                0x0042: "tk",
                0x0043: "uz",
                0x0044: "tt",
                0x0045: "bn",
                0x0046: "pa",
                0x0047: "gu",
                0x0048: "or",
                0x0049: "ta",
                0x004A: "te",
                0x004B: "kn",
                0x004C: "ml",
                0x004D: "as",
                0x004E: "mr",
                0x004F: "sa",
                0x0050: "mn",
                0x0051: "bo",
                0x0052: "cy",
                0x0053: "km",
                0x0054: "lo",
                0x0055: "my",
                0x0056: "gl",
                0x0057: "kok",
                0x0058: "mni",
                0x0059: "sd",
                0x005A: "syr",
                0x005B: "si",
                0x005C: "chr",
                0x005D: "iu",
                0x005E: "am",
                0x005F: "tzm",
                0x0060: "ks",
                0x0061: "ne",
                0x0062: "fy",
                0x0063: "ps",
                0x0064: "fil",
                0x0065: "dv",
                0x0066: "bin",
                0x0067: "ff",
                0x0068: "ha",
                0x0069: "ibb",
                0x006A: "yo",
                0x006B: "quz",
                0x006C: "nso",
                0x006D: "ba",
                0x006E: "lb",
                0x006F: "kl",
                0x0070: "ig",
                0x0071: "kr",
                0x0072: "om",
                0x0073: "ti",
                0x0074: "gn",
                0x0075: "haw",
                0x0076: "la",
                0x0077: "so",
                0x0078: "ii",
                0x0079: "pap",
                0x007A: "arn",
                0x007C: "moh",
                0x007E: "br",
                0x0080: "ug",
                0x0081: "mi",
                0x0082: "oc",
                0x0083: "co",
                0x0084: "gsw",
                0x0085: "sah",
                0x0086: "qut",
                0x0087: "rw",
                0x0088: "wo",
                0x008C: "prs",
                0x0091: "gd",
                0x0092: "ku",
                0x0093: "quc",
                0x0401: "ar-SA",
                0x0402: "bg-BG",
                0x0403: "ca-ES",
                0x0404: "zh-TW",
                0x0405: "cs-CZ",
                0x0406: "da-DK",
                0x0407: "de-DE",
                0x0408: "el-GR",
                0x0409: "en-US",
                0x040A: "es-ES_tradnl",
                0x040B: "fi-FI",
                0x040C: "fr-FR",
                0x040D: "he-IL",
                0x040E: "hu-HU",
                0x040F: "is-IS",
                0x0410: "it-IT",
                0x0411: "ja-JP",
                0x0412: "ko-KR",
                0x0413: "nl-NL",
                0x0414: "nb-NO",
                0x0415: "pl-PL",
                0x0416: "pt-BR",
                0x0417: "rm-CH",
                0x0418: "ro-RO",
                0x0419: "ru-RU",
                0x041A: "hr-HR",
                0x041B: "sk-SK",
                0x041C: "sq-AL",
                0x041D: "sv-SE",
                0x041E: "th-TH",
                0x041F: "tr-TR",
                0x0420: "ur-PK",
                0x0421: "id-ID",
                0x0422: "uk-UA",
                0x0423: "be-BY",
                0x0424: "sl-SI",
                0x0425: "et-EE",
                0x0426: "lv-LV",
                0x0427: "lt-LT",
                0x0428: "tg-Cyrl-TJ",
                0x0429: "fa-IR",
                0x042A: "vi-VN",
                0x042B: "hy-AM",
                0x042C: "az-Latn-AZ",
                0x042D: "eu-ES",
                0x042E: "hsb-DE",
                0x042F: "mk-MK",
                0x0430: "st-ZA",
                0x0431: "ts-ZA",
                0x0432: "tn-ZA",
                0x0433: "ve-ZA",
                0x0434: "xh-ZA",
                0x0435: "zu-ZA",
                0x0436: "af-ZA",
                0x0437: "ka-GE",
                0x0438: "fo-FO",
                0x0439: "hi-IN",
                0x043A: "mt-MT",
                0x043B: "se-NO",
                0x043D: "yi-001",
                0x043E: "ms-MY",
                0x043F: "kk-KZ",
                0x0440: "ky-KG",
                0x0441: "sw-KE",
                0x0442: "tk-TM",
                0x0443: "uz-Latn-UZ",
                0x0444: "tt-RU",
                0x0445: "bn-IN",
                0x0446: "pa-IN",
                0x0447: "gu-IN",
                0x0448: "or-IN",
                0x0449: "ta-IN",
                0x044A: "te-IN",
                0x044B: "kn-IN",
                0x044C: "ml-IN",
                0x044D: "as-IN",
                0x044E: "mr-IN",
                0x044F: "sa-IN",
                0x0450: "mn-MN",
                0x0451: "bo-CN",
                0x0452: "cy-GB",
                0x0453: "km-KH",
                0x0454: "lo-LA",
                0x0455: "my-MM",
                0x0456: "gl-ES",
                0x0457: "kok-IN",
                0x0458: "mni-IN",
                0x0459: "sd-Deva-IN",
                0x045A: "syr-SY",
                0x045B: "si-LK",
                0x045C: "chr-Cher-US",
                0x045D: "iu-Cans-CA",
                0x045E: "am-ET",
                0x045F: "tzm-Arab-MA",
                0x0460: "ks-Arab",
                0x0461: "ne-NP",
                0x0462: "fy-NL",
                0x0463: "ps-AF",
                0x0464: "fil-PH",
                0x0465: "dv-MV",
                0x0466: "bin-NG",
                0x0467: "ff-NG",
                0x0468: "ha-Latn-NG",
                0x0469: "ibb-NG",
                0x046A: "yo-NG",
                0x046B: "quz-BO",
                0x046C: "nso-ZA",
                0x046D: "ba-RU",
                0x046E: "lb-LU",
                0x046F: "kl-GL",
                0x0470: "ig-NG",
                0x0471: "kr-Latn-NG",
                0x0472: "om-ET",
                0x0473: "ti-ET",
                0x0474: "gn-PY",
                0x0475: "haw-US",
                0x0476: "la-VA",
                0x0477: "so-SO",
                0x0478: "ii-CN",
                0x0479: "pap-029",
                0x047A: "arn-CL",
                0x047C: "moh-CA",
                0x047E: "br-FR",
                0x0480: "ug-CN",
                0x0481: "mi-NZ",
                0x0482: "oc-FR",
                0x0483: "co-FR",
                0x0484: "gsw-FR",
                0x0485: "sah-RU",
                0x0486: "qut-GT",
                0x0487: "rw-RW",
                0x0488: "wo-SN",
                0x048C: "prs-AF",
                0x048D: "plt-MG",
                0x048E: "zh-yue-HK",
                0x048F: "tdd-Tale-CN",
                0x0490: "khb-Talu-CN",
                0x0491: "gd-GB",
                0x0492: "ku-Arab-IQ",
                0x0493: "quc-CO",
                0x0501: "qps-ploc",
                0x05FE: "qps-ploca",
                0x0801: "ar-IQ",
                0x0803: "ca-ES-valencia",
                0x0804: "zh-CN",
                0x0807: "de-CH",
                0x0809: "en-GB",
                0x080A: "es-MX",
                0x080C: "fr-BE",
                0x0810: "it-CH",
                0x0811: "ja-Ploc-JP",
                0x0813: "nl-BE",
                0x0814: "nn-NO",
                0x0816: "pt-PT",
                0x0818: "ro-MD",
                0x0819: "ru-MD",
                0x081A: "sr-Latn-CS",
                0x081D: "sv-FI",
                0x0820: "ur-IN",
                0x082C: "az-Cyrl-AZ",
                0x082E: "dsb-DE",
                0x0832: "tn-BW",
                0x083B: "se-SE",
                0x083C: "ga-IE",
                0x083E: "ms-BN",
                0x083F: "kk-Latn-KZ",
                0x0843: "uz-Cyrl-UZ",
                0x0845: "bn-BD",
                0x0846: "pa-Arab-PK",
                0x0849: "ta-LK",
                0x0850: "mn-Mong-CN",
                0x0851: "bo-BT",
                0x0859: "sd-Arab-PK",
                0x085D: "iu-Latn-CA",
                0x085F: "tzm-Latn-DZ",
                0x0860: "ks-Deva-IN",
                0x0861: "ne-IN",
                0x0867: "ff-Latn-SN",
                0x086B: "quz-EC",
                0x0873: "ti-ER",
                0x09FF: "qps-plocm",
                0x0C01: "ar-EG",
                0x0C04: "zh-HK",
                0x0C07: "de-AT",
                0x0C09: "en-AU",
                0x0C0A: "es-ES",
                0x0C0C: "fr-CA",
                0x0C1A: "sr-Cyrl-CS",
                0x0C3B: "se-FI",
                0x0C50: "mn-Mong-MN",
                0x0C51: "dz-BT",
                0x0C5F: "tmz-MA",
                0x0C6B: "quz-PE",
                0x1001: "ar-LY",
                0x1004: "zh-SG",
                0x1007: "de-LU",
                0x1009: "en-CA",
                0x100A: "es-GT",
                0x100C: "fr-CH",
                0x101A: "hr-BA",
                0x103B: "smj-NO",
                0x105F: "tzm-Tfng-MA",
                0x1401: "ar-DZ",
                0x1404: "zh-MO",
                0x1407: "de-LI",
                0x1409: "en-NZ",
                0x140A: "es-CR",
                0x140C: "fr-LU",
                0x141A: "bs-Latn-BA",
                0x143B: "smj-SE",
                0x1801: "ar-MA",
                0x1809: "en-IE",
                0x180A: "es-PA",
                0x180C: "fr-MC",
                0x181A: "sr-Latn-BA",
                0x183B: "sma-NO",
                0x1C01: "ar-TN",
                0x1C09: "en-ZA",
                0x1C0A: "es-DO",
                0x1C0C: "fr-029",
                0x1C1A: "sr-Cyrl-BA",
                0x1C3B: "sma-SE",
                0x2001: "ar-OM",
                0x2009: "en-JM",
                0x200A: "es-VE",
                0x200C: "fr-RE",
                0x201A: "bs-Cyrl-BA",
                0x203B: "sms-FI",
                0x2401: "ar-YE",
                0x2409: "en-029",
                0x240A: "es-CO",
                0x240C: "fr-CD",
                0x241A: "sr-Latn-RS",
                0x243B: "smn-FI",
                0x2801: "ar-SY",
                0x2809: "en-BZ",
                0x280A: "es-PE",
                0x280C: "fr-SN",
                0x281A: "sr-Cyrl-RS",
                0x2C01: "ar-JO",
                0x2C09: "en-TT",
                0x2C0A: "es-AR",
                0x2C0C: "fr-CM",
                0x2C1A: "sr-Latn-ME",
                0x3001: "ar-LB",
                0x3009: "en-ZW",
                0x300A: "es-EC",
                0x300C: "fr-CI",
                0x301A: "sr-Cyrl-ME",
                0x3401: "ar-KW",
                0x3409: "en-PH",
                0x340A: "es-CL",
                0x340C: "fr-ML",
                0x3801: "ar-AE",
                0x3809: "en-ID",
                0x380A: "es-UY",
                0x380C: "fr-MA",
                0x3C01: "ar-BH",
                0x3C09: "en-HK",
                0x3C0A: "es-PY",
                0x3C0C: "fr-HT",
                0x4001: "ar-QA",
                0x4009: "en-IN",
                0x400A: "es-BO",
                0x4401: "ar-Ploc-SA",
                0x4409: "en-MY",
                0x440A: "es-SV",
                0x4801: "ar-145",
                0x4809: "en-SG",
                0x480A: "es-HN",
                0x4C09: "en-AE",
                0x4C0A: "es-NI",
                0x5009: "en-BH",
                0x500A: "es-PR",
                0x5409: "en-EG",
                0x540A: "es-US",
                0x5809: "en-JO",
                0x580A: "es-419",
                0x5C09: "en-KW",
                0x5C0A: "es-CU",
                0x6009: "en-TR",
                0x6409: "en-YE",
                0x641A: "bs-Cyrl",
                0x681A: "bs-Latn",
                0x6C1A: "sr-Cyrl",
                0x701A: "sr-Latn",
                0x703B: "smn",
                0x742C: "az-Cyrl",
                0x743B: "sms",
                0x7804: "zh",
                0x7814: "nn",
                0x781A: "bs",
                0x782C: "az-Latn",
                0x783B: "sma",
                0x783F: "kk-Cyrl",
                0x7843: "uz-Cyrl",
                0x7850: "mn-Cyrl",
                0x785D: "iu-Cans",
                0x785F: "tzm-Tfng",
                0x7C04: "zh-Hant",
                0x7C14: "nb",
                0x7C1A: "sr",
                0x7C28: "tg-Cyrl",
                0x7C2E: "dsb",
                0x7C3B: "smj",
                0x7C3F: "kk-Latn",
                0x7C43: "uz-Latn",
                0x7C46: "pa-Arab",
                0x7C50: "mn-Mong",
                0x7C59: "sd-Arab",
                0x7C5C: "chr-Cher",
                0x7C5D: "iu-Latn",
                0x7C5F: "tzm-Latn",
                0x7C67: "ff-Latn",
                0x7C68: "ha-Latn",
                0x7C92: "ku-Arab",
                0xE40C: "fr-015",
            }
        }
    }

    # Style Flags:
    # https://docs.microsoft.com/en-us/typography/opentype/spec/head
    # https://docs.microsoft.com/en-us/typography/opentype/spec/os2#fsselection
    STYLE_FLAG_REGULAR: str = "regular"
    STYLE_FLAG_BOLD: str = "bold"
    STYLE_FLAG_ITALIC: str = "italic"
    STYLE_FLAG_UNDERLINE: str = "underline"
    STYLE_FLAG_OUTLINE: str = "outline"
    STYLE_FLAG_SHADOW: str = "shadow"
    STYLE_FLAG_CONDENSED: str = "condensed"
    STYLE_FLAG_EXTENDED: str = "extended"
    _STYLE_FLAGS: dict[str, dict[str, Any]] = {
        STYLE_FLAG_REGULAR: {"bit_head_mac": None, "bit_os2_fs": 6},
        STYLE_FLAG_BOLD: {"bit_head_mac": 0, "bit_os2_fs": 5},
        STYLE_FLAG_ITALIC: {"bit_head_mac": 1, "bit_os2_fs": 0},
        STYLE_FLAG_UNDERLINE: {"bit_head_mac": 2, "bit_os2_fs": None},
        STYLE_FLAG_OUTLINE: {"bit_head_mac": 3, "bit_os2_fs": 3},
        STYLE_FLAG_SHADOW: {"bit_head_mac": 4, "bit_os2_fs": None},
        STYLE_FLAG_CONDENSED: {"bit_head_mac": 5, "bit_os2_fs": None},
        STYLE_FLAG_EXTENDED: {"bit_head_mac": 6, "bit_os2_fs": None},
    }
    _STYLE_FLAGS_KEYS: list[str] = list(_STYLE_FLAGS.keys())

    # Unicode blocks/scripts data:
    _UNICODE_BLOCKS: list[dict[str, Any]] = read_json("data/unicode-blocks.json")
    _UNICODE_SCRIPTS: list[dict[str, Any]] = read_json("data/unicode-scripts.json")

    # Variable Axes:
    _VARIABLE_AXES: list[dict[str, Any]] = [
        {"tag": "ital", "name": "Italic"},
        {"tag": "opsz", "name": "Optical Size"},
        {"tag": "slnt", "name": "Slant"},
        {"tag": "wdth", "name": "Width"},
        {"tag": "wght", "name": "Weight"},
        # https://fonts.google.com/variablefonts#axis-definitions
        {"tag": "ARRR", "name": "AR Retinal Resolution"},
        {"tag": "YTAS", "name": "Ascender Height"},
        {"tag": "BLED", "name": "Bleed"},
        {"tag": "BNCE", "name": "Bounce"},
        {"tag": "CASL", "name": "Casual"},
        {"tag": "XTRA", "name": "Counter Width"},
        {"tag": "CRSV", "name": "Cursive"},
        {"tag": "YTDE", "name": "Descender Depth"},
        {"tag": "EHLT", "name": "Edge Highlight"},
        {"tag": "ELGR", "name": "Element Grid"},
        {"tag": "ELSH", "name": "Element Shape"},
        {"tag": "EDPT", "name": "Extrusion Depth"},
        {"tag": "YTFI", "name": "Figure Height"},
        {"tag": "XPRN", "name": "Expression"}, # Removed: https://github.com/google/fonts/pull/2594
        {"tag": "FILL", "name": "Fill"},
        {"tag": "GRAD", "name": "Grade"},
        {"tag": "HEXP", "name": "Hyper Expansion"},
        {"tag": "INFM", "name": "Informality"},
        {"tag": "YTLC", "name": "Lowercase Height"},
        {"tag": "MONO", "name": "Monospace"},
        {"tag": "MORF", "name": "Morph"},
        {"tag": "XROT", "name": "Rotation in X"},
        {"tag": "YROT", "name": "Rotation in Y"},
        {"tag": "ZROT", "name": "Rotation in Z"},
        {"tag": "ROND", "name": "Roundness"},
        {"tag": "SCAN", "name": "Scanlines"},
        {"tag": "SHLN", "name": "Shadow Length"},
        {"tag": "SHRP", "name": "Sharpness"},
        {"tag": "SOFT", "name": "Softness"},
        {"tag": "SPAC", "name": "Spacing"},
        {"tag": "XOPQ", "name": "Thick Stroke"},
        {"tag": "YOPQ", "name": "Thin Stroke"},
        {"tag": "YTUC", "name": "Uppercase Height"},
        {"tag": "YELA", "name": "Vertical Element Alignment"},
        {"tag": "VOLM", "name": "Volume"},
        {"tag": "WONK", "name": "Wonky"},
        {"tag": "YEAR", "name": "Year"},
    ]
    _VARIABLE_AXES_BY_TAG: dict[str, Any] = {
        axis["tag"]: axis for axis in _VARIABLE_AXES
    }

    # Vertical Metrics:
    VERTICAL_METRIC_UNITS_PER_EM: str = "units_per_em"
    VERTICAL_METRIC_Y_MAX: str = "y_max"
    VERTICAL_METRIC_Y_MIN: str = "y_min"
    VERTICAL_METRIC_ASCENT: str = "ascent"
    VERTICAL_METRIC_DESCENT: str = "descent"
    VERTICAL_METRIC_LINE_GAP: str = "line_gap"
    VERTICAL_METRIC_TYPO_ASCENDER: str = "typo_ascender"
    VERTICAL_METRIC_TYPO_DESCENDER: str = "typo_descender"
    VERTICAL_METRIC_TYPO_LINE_GAP: str = "typo_line_gap"
    VERTICAL_METRIC_CAP_HEIGHT: str = "cap_height"
    VERTICAL_METRIC_X_HEIGHT: str = "x_height"
    VERTICAL_METRIC_WIN_ASCENT: str = "win_ascent"
    VERTICAL_METRIC_WIN_DESCENT: str = "win_descent"
    # fmt: off
    _VERTICAL_METRICS: list[dict[str, Any]] = [
        {"table": "head", "attr": "unitsPerEm", "key": VERTICAL_METRIC_UNITS_PER_EM},
        {"table": "head", "attr": "yMax", "key": VERTICAL_METRIC_Y_MAX},
        {"table": "head", "attr": "yMin", "key": VERTICAL_METRIC_Y_MIN},
        {"table": "hhea", "attr": "ascent", "key": VERTICAL_METRIC_ASCENT},
        {"table": "hhea", "attr": "descent", "key": VERTICAL_METRIC_DESCENT},
        {"table": "hhea", "attr": "lineGap", "key": VERTICAL_METRIC_LINE_GAP},
        {"table": "OS/2", "attr": "sTypoAscender", "key": VERTICAL_METRIC_TYPO_ASCENDER},
        {"table": "OS/2", "attr": "sTypoDescender", "key": VERTICAL_METRIC_TYPO_DESCENDER},
        {"table": "OS/2", "attr": "sTypoLineGap", "key": VERTICAL_METRIC_TYPO_LINE_GAP},
        {"table": "OS/2", "attr": "sCapHeight", "key": VERTICAL_METRIC_CAP_HEIGHT},
        {"table": "OS/2", "attr": "sxHeight", "key": VERTICAL_METRIC_X_HEIGHT},
        {"table": "OS/2", "attr": "usWinAscent", "key": VERTICAL_METRIC_WIN_ASCENT},
        {"table": "OS/2", "attr": "usWinDescent", "key": VERTICAL_METRIC_WIN_DESCENT},
    ]
    # fmt: on

    # Weights:
    # https://docs.microsoft.com/en-us/typography/opentype/otspec170/os2#usweightclass
    WEIGHT_EXTRA_THIN: str = "Extra-thin"  # (Hairline)
    WEIGHT_THIN: str = "Thin"
    WEIGHT_EXTRA_LIGHT: str = "Extra-light"  # (Ultra-light)
    WEIGHT_LIGHT: str = "Light"
    WEIGHT_REGULAR: str = "Regular"  # (Normal)
    WEIGHT_BOOK: str = "Book"
    WEIGHT_MEDIUM: str = "Medium"
    WEIGHT_SEMI_BOLD: str = "Semi-bold"  # (Demi-bold)
    WEIGHT_BOLD: str = "Bold"
    WEIGHT_EXTRA_BOLD: str = "Extra-bold"  # (Ultra-bold)
    WEIGHT_BLACK: str = "Black"  # (Heavy)
    WEIGHT_EXTRA_BLACK: str = "Extra-black"  # (Nord)
    _WEIGHTS: list[dict[str, Any]] = [
        {"value": 50, "name": WEIGHT_EXTRA_THIN},
        {"value": 100, "name": WEIGHT_THIN},
        {"value": 200, "name": WEIGHT_EXTRA_LIGHT},
        {"value": 300, "name": WEIGHT_LIGHT},
        {"value": 400, "name": WEIGHT_REGULAR},
        {"value": 450, "name": WEIGHT_BOOK},
        {"value": 500, "name": WEIGHT_MEDIUM},
        {"value": 600, "name": WEIGHT_SEMI_BOLD},
        {"value": 700, "name": WEIGHT_BOLD},
        {"value": 800, "name": WEIGHT_EXTRA_BOLD},
        {"value": 900, "name": WEIGHT_BLACK},
        {"value": 950, "name": WEIGHT_EXTRA_BLACK},
    ]
    _WEIGHTS_BY_VALUE: dict[int, dict[str, Any]] = {
        weight["value"]: weight for weight in _WEIGHTS
    }

    # Widths:
    # https://docs.microsoft.com/en-us/typography/opentype/otspec170/os2#uswidthclass
    WIDTH_ULTRA_CONDENSED: str = "Ultra-condensed"
    WIDTH_EXTRA_CONDENSED: str = "Extra-condensed"
    WIDTH_CONDENSED: str = "Condensed"
    WIDTH_SEMI_CONDENSED: str = "Semi-condensed"
    WIDTH_MEDIUM: str = "Medium"  # (Normal)
    WIDTH_SEMI_EXPANDED: str = "Semi-expanded"
    WIDTH_EXPANDED: str = "Expanded"
    WIDTH_EXTRA_EXPANDED: str = "Extra-expanded"
    WIDTH_ULTRA_EXPANDED: str = "Ultra-expanded"
    _WIDTHS: list[dict[str, Any]] = [
        {"value": 1, "perc": 50.0, "name": WIDTH_ULTRA_CONDENSED},
        {"value": 2, "perc": 62.5, "name": WIDTH_EXTRA_CONDENSED},
        {"value": 3, "perc": 75.0, "name": WIDTH_CONDENSED},
        {"value": 4, "perc": 87.5, "name": WIDTH_SEMI_CONDENSED},
        {"value": 5, "perc": 100.0, "name": WIDTH_MEDIUM},
        {"value": 6, "perc": 112.5, "name": WIDTH_SEMI_EXPANDED},
        {"value": 7, "perc": 125.0, "name": WIDTH_EXPANDED},
        {"value": 8, "perc": 150.0, "name": WIDTH_EXTRA_EXPANDED},
        {"value": 9, "perc": 200.0, "name": WIDTH_ULTRA_CONDENSED},
    ]
    _WIDTHS_BY_VALUE: dict[int, dict[str, Any]] = {
        width["value"]: width for width in _WIDTHS
    }

    def __init__(
        self,
        filepath: str | Path | IO | TTFont | Font,
        **kwargs: Any,
    ) -> None:
        """
        Constructs a new Font instance loading a font file from the given filepath.

        :param filepath: The filepath from which to load the font
        :type filepath: string or file object or TTFont or Font

        :raises ValueError: if the filepath is not a valid font
        """
        super().__init__()

        self._filepath: str | Path | None = None
        self._fileobject: IO | None = None
        self._ttfont: TTFont | None = None
        self._kwargs: dict[str, Any] = {}

        if isinstance(filepath, (Path, str)):
            self._init_with_filepath(str(filepath), **kwargs)
        elif hasattr(filepath, "read"):
            self._init_with_fileobject(filepath, **kwargs)
        elif isinstance(filepath, Font):
            self._init_with_font(filepath, **kwargs)
        elif isinstance(filepath, TTFont):
            self._init_with_ttfont(filepath, **kwargs)
        else:
            filepath_type = type(filepath).__name__
            raise ArgumentError(
                "Invalid filepath type: "
                "expected str or pathlib.Path or file object or TTFont or Font, "
                f"found '{filepath_type}'."
            )

    def _init_with_filepath(
        self,
        filepath: str | Path,
        **kwargs: Any,
    ) -> None:
        try:
            self._filepath = filepath
            self._kwargs = kwargs
            self._ttfont = TTFont(self._filepath, **kwargs)

        except TTLibError as error:
            raise ArgumentError(f"Invalid font at filepath: '{filepath}'.") from error

    def _init_with_fileobject(
        self,
        fileobject: IO,
        **kwargs: Any,
    ) -> None:
        try:
            self._fileobject = fileobject
            self._kwargs = kwargs
            self._ttfont = TTFont(self._fileobject, **kwargs)

        except TTLibError as error:
            raise ArgumentError(
                f"Invalid font at fileobject: '{fileobject}'."
            ) from error

    def _init_with_font(
        self,
        font: Font,
        **kwargs: Any,
    ) -> None:
        self._init_with_ttfont(font.get_ttfont())

    def _init_with_ttfont(
        self,
        ttfont: TTFont,
        **kwargs: Any,
    ) -> None:
        self._fileobject = BytesIO()
        ttfont.save(self._fileobject)
        self._ttfont = TTFont(self._fileobject, **kwargs)
        self._kwargs = kwargs

    def __enter__(
        self,
    ) -> Font:
        return self

    def __exit__(  # type: ignore
        self,
        e_type,
        e_value,
        e_traceback,
    ) -> None:
        self.close()

    def clone(
        self,
    ) -> Font:
        """
        Creates a new Font instance reading the same binary file.
        """
        return Font(self._filepath or self._fileobject, **self._kwargs)

    def close(
        self,
    ) -> None:
        """
        Close the wrapped TTFont instance.
        """
        font = self.get_ttfont()
        font.close()

    @classmethod
    def from_collection(
        cls,
        filepath: str | Path,
        **kwargs: Any,
    ) -> list[Font]:
        """
        Gets a list of Font objects from a font collection file (.ttc / .otc)

        :param filepath: The filepath
        :type filepath: str or pathlib.Path

        :returns: A list of Font objects.
        :rtype: list
        """
        filepath = str(filepath)
        fonts = []
        with TTCollection(filepath) as font_collection:
            fonts = [cls(font, **kwargs) for font in font_collection]
        return fonts

    def get_characters(
        self,
        *,
        ignore_blank: bool = False,
    ) -> Generator[dict[str, Any], None, None]:
        """
        Gets the font characters.

        :param ignore_blank: If True, characters without contours will not be returned.
        :type ignore_blank: bool

        :returns: The characters.
        :rtype: generator of dicts

        :raises TypeError: If it's not possible to find the 'best' unicode cmap dict.
        """
        font = self.get_ttfont()
        cmap = font.getBestCmap()
        if cmap is None:
            raise DataError("Unable to find the 'best' unicode cmap dict.")
        glyfs = font.get("glyf")
        for code, char_name in cmap.items():
            code_hex = f"{code:04X}"
            if 0 <= code < 0x110000:
                char = chr(code)
            else:
                continue
            if ascii.iscntrl(char):
                continue
            if glyfs and ignore_blank:
                glyf = glyfs.get(char_name)
                if glyf and glyf.numberOfContours == 0:
                    continue
            unicode_name = unicodedata.name(char, None)
            unicode_block_name = unicodedata.block(code)
            unicode_script_tag = unicodedata.script(code)
            unicode_script_name = unicodedata.script_name(unicode_script_tag)
            yield {
                "character": char,
                "character_name": char_name,
                "code": code,
                "escape_sequence": f"\\u{code_hex}",
                "html_code": f"&#{code};",
                "unicode": f"U+{code_hex}",
                "unicode_code": code,
                "unicode_name": unicode_name,
                "unicode_block_name": unicode_block_name,
                "unicode_script_name": unicode_script_name,
                "unicode_script_tag": unicode_script_tag,
            }

    def get_characters_count(
        self,
        *,
        ignore_blank: bool = False,
    ) -> int:
        """
        Gets the font characters count.

        :param ignore_blank: If True, characters without contours will not be counted.
        :type ignore_blank: bool

        :returns: The characters count.
        :rtype: int
        """
        return len(list(self.get_characters(ignore_blank=ignore_blank)))

    def _get_family_classification_items(
        self,
        class_id: int | str,
        subclass_id: int | str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        classes_list = self._FAMILY_CLASSIFICATIONS["classes"]
        class_item = find_item(
            items_list=classes_list,
            key=lambda item: item.get("id") == class_id,
        )
        subclasses_list = class_item.get("subclasses", [])
        subclass_item = find_item(
            items_list=subclasses_list,
            key=lambda item: item.get("id") == subclass_id,
        )
        return (class_item, subclass_item)

    def get_family_classification(
        self,
    ) -> dict[str, Any] | None:
        """
        Gets the font family classification info reading
        the sFamilyClass field from the OS/2 table.
        If the OS/2 table is not available None is returned.

        :returns: A dictionary containing the font family classification info, e.g.
            {
                "full_name": "Sans Serif / Neo-grotesque Gothic",
                "class_id": 8,
                "class_name": "Sans Serif",
                "subclass_id": 5,
                "subclass_name": "Neo-grotesque Gothic",
            }
        :rtype: dict
        """
        font = self.get_ttfont()
        os2 = font.get("OS/2")
        if not os2:
            return None
        class_id = os2.sFamilyClass >> 8  # (or // 256)
        subclass_id = os2.sFamilyClass & 0xFF  # (or % 256)

        class_item, subclass_item = self._get_family_classification_items(
            class_id=class_id,
            subclass_id=subclass_id,
        )
        # class_id = class_item.get("id", "")
        class_name = class_item.get("name", "")
        # subclass_id = subclass_item.get("id", "")
        subclass_name = subclass_item.get("name", "")
        full_name = concat_names(class_name, subclass_name, separator=" / ")

        return {
            "full_name": full_name,
            "class_id": class_id,
            "class_name": class_name,
            "subclass_id": subclass_id,
            "subclass_name": subclass_name,
        }

    def get_family_name(
        self,
    ) -> str:
        """
        Gets the family name reading the name records with priority order (16, 21, 1).

        :returns: The font family name.
        :rtype: str
        """
        return (
            self.get_name(self.NAME_TYPOGRAPHIC_FAMILY_NAME)
            or self.get_name(self.NAME_WWS_FAMILY_NAME)
            or self.get_name(self.NAME_FAMILY_NAME)
            or ""
        )

    def get_features(
        self,
    ) -> list[dict[str, Any]]:
        """
        Gets the font opentype features.

        :returns: The features list.
        :rtype: list of dict
        """
        features_tags = self.get_features_tags()
        return [
            self._FEATURES_BY_TAG.get(features_tag, {}).copy()
            for features_tag in features_tags
            if features_tag in self._FEATURES_BY_TAG
        ]

    def get_features_tags(
        self,
    ) -> list[str]:
        """
        Gets the font opentype features tags.

        :returns: The features tags list.
        :rtype: list of str
        """
        font = self.get_ttfont()
        features_tags = set()
        for table_tag in ["GPOS", "GSUB"]:
            if table_tag in font:
                table = font[table_tag].table
                try:
                    feature_record = table.FeatureList.FeatureRecord or []
                except AttributeError:
                    feature_record = []
                for feature in feature_record:
                    features_tags.add(feature.FeatureTag)
        return sorted(features_tags)

    def get_filename(
        self,
        *,
        variable_suffix: str = "Variable",
        variable_axes_tags: bool = True,
        variable_axes_values: bool = False,
    ) -> str:
        """
        Gets the filename to use for saving the font to file-system.

        :param variable_suffix: The variable suffix, default "Variable"
        :type variable_suffix: str
        :param variable_axes_tags: The variable axes tags flag,
            if True, the axes tags will be appended, eg '[wght,wdth]'
        :type variable_axes_tags: bool
        :param variable_axes_values: The variable axes values flag
            if True, each axis values will be appended, eg '[wght(100,100,900),wdth(75,100,125)]'
        :type variable_axes_values: bool

        :returns: The filename.
        :rtype: str
        """
        if self.is_variable():
            family_name = self.get_family_name()
            family_name = remove_spaces(family_name)
            subfamily_name = self.get_name(Font.NAME_SUBFAMILY_NAME) or ""
            basename = family_name
            # append subfamily name
            if subfamily_name.lower() in ("bold", "bold italic", "italic"):
                subfamily_name = remove_spaces(subfamily_name.lower().title())
                basename = f"{basename}-{subfamily_name}"
            # append variable suffix
            variable_suffix = (variable_suffix or "").strip()
            if variable_suffix:
                if variable_suffix.lower() not in basename.lower():
                    basename = f"{basename}-{variable_suffix}"
            # append axis tags stringified suffix, eg. [wdth,wght,slnt]
            if variable_axes_tags:
                axes = self.get_variable_axes() or []
                axes_str_parts = []
                for axis in axes:
                    axis_tag = axis["tag"]
                    axis_str = f"{axis_tag}"
                    if variable_axes_values:
                        axis_min_value = int(axis["min_value"])
                        axis_default_value = int(axis["default_value"])
                        axis_max_value = int(axis["max_value"])
                        axis_str += (
                            f"({axis_min_value},{axis_default_value},{axis_max_value})"
                        )
                    axes_str_parts.append(axis_str)
                axes_str = ",".join(axes_str_parts)
                axes_str = f"[{axes_str}]"
                basename = f"{basename}{axes_str}"
        else:
            family_name = self.get_family_name()
            family_name = remove_spaces(family_name)
            style_name = self.get_style_name()
            style_name = remove_spaces(style_name)
            basename = concat_names(family_name, style_name, separator="-")
        extension = self.get_format()
        filename = f"{basename}.{extension}"
        return filename

    def get_fingerprint(  # type: ignore
        self,
        *,
        text: str = "",
    ):
        """
        Gets the font fingerprint: an hash calculated from an image representation of the font.
        Changing the text option affects the returned fingerprint.

        :param text: The text used for generating the fingerprint,
        default value: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789".
        :type text: str

        :returns: The fingerprint hash.
        :rtype: imagehash.ImageHash
        """
        import imagehash

        text = text or "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"

        img = self.get_image(text=text, size=72)
        img_size = img.size
        img = img.resize((img_size[0] // 2, img_size[1] // 2))
        img = img.resize((img_size[0], img_size[1]), Image.Resampling.NEAREST)
        img = img.quantize(colors=8)
        # img.show()

        hash = imagehash.average_hash(img, hash_size=64)
        return hash

    def get_fingerprint_match(  # type: ignore
        self,
        other: Font | str,
        *,
        tolerance: int = 10,
        text: str = "",
    ):
        """
        Gets the fingerprint match between this font and another one.
        by checking if their fingerprints are equal (difference <= tolerance).

        :param other: The other font, can be either a filepath or a Font instance.
        :type other: str or Font
        :param tolerance: The diff tolerance, default 3.
        :type tolerance: int
        :param text: The text used for generating the fingerprint,
        default value: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789".
        :type text: str

        :returns: A tuple containing the match info (match, diff, hash, other_hash).
        :rtype: tuple
        """
        other_font = None
        if isinstance(other, str):
            other_font = Font(other)
        elif isinstance(other, Font):
            other_font = other
        else:
            other_type = type(other).__name__
            raise ArgumentError(
                "Invalid other filepath/font: expected str or Font instance, "
                f"found '{other_type}'."
            )
        hash = self.get_fingerprint(text=text)
        other_hash = other_font.get_fingerprint(text=text)
        diff = hash - other_hash
        match = diff <= tolerance
        match = match and self.is_variable() == other_font.is_variable()
        return (match, diff, hash, other_hash)

    def get_format(
        self,
        *,
        ignore_flavor: bool = False,
    ) -> str:
        """
        Gets the font format: otf, ttf, woff, woff2.

        :param ignore_flavor: If True, the original format without compression will be returned.
        :type ignore_flavor: bool

        :returns: The format.
        :rtype: str
        """
        font = self.get_ttfont()
        version = font.sfntVersion
        flavor = font.flavor
        format_ = ""
        if flavor in [self.FORMAT_WOFF, self.FORMAT_WOFF2] and not ignore_flavor:
            format_ = str(flavor)
        elif version == "OTTO" and ("CFF " in font or "CFF2" in font):
            format_ = self.FORMAT_OTF
        elif version == "\0\1\0\0":
            format_ = self.FORMAT_TTF
        elif version == "wOFF":
            format_ = self.FORMAT_WOFF
        elif version == "wOF2":
            format_ = self.FORMAT_WOFF2
        if not format_:
            raise DataError("Unable to get the font format.")
        return format_

    def get_glyphs(
        self,
    ) -> Generator[dict[str, Any], None, None]:
        """
        Gets the font glyphs and their own composition.

        :returns: The glyphs.
        :rtype: generator of dicts
        """
        font = self.get_ttfont()
        glyfs = font["glyf"]
        glyphset = font.getGlyphSet()
        for name in glyphset.keys():
            glyf = glyfs[name]
            yield {
                "name": name,
                "components_names": glyf.getComponentNames(glyfs),
            }

    def get_glyphs_count(
        self,
    ) -> int:
        """
        Gets the font glyphs count.

        :returns: The glyphs count.
        :rtype: int
        """
        font = self.get_ttfont()
        glyphset = font.getGlyphSet()
        count = len(glyphset)
        return count

    def get_image(  # type: ignore
        self,
        *,
        text: str,
        size: int,
        color: tuple[int, int, int, int] = (0, 0, 0, 255),
        background_color: tuple[int, int, int, int] = (255, 255, 255, 255),
    ):
        """
        Gets an image representation of the font rendering
        some text using the given options.

        :param text: The text rendered in the image
        :type text: str
        :param size: The font size
        :type size: int
        :param color: The text color
        :type color: tuple
        :param background_color: The background color
        :type background_color: tuple

        :returns: The image.
        :rtype: PIL.Image
        """
        with tempfile.TemporaryDirectory() as dest:
            filepath = self.save(dest)
            img = Image.new("RGBA", (2, 2), background_color)
            draw = ImageDraw.Draw(img)
            img_font = ImageFont.truetype(filepath, size)
            img_bbox = draw.textbbox((0, 0), text, font=img_font)
            img_width = img_bbox[2] - img_bbox[0]
            img_height = img_bbox[3] - img_bbox[1]
            img_size = (img_width, img_height)
            img = img.resize(img_size)
            draw = ImageDraw.Draw(img)
            draw.text((-img_bbox[0], -img_bbox[1]), text, font=img_font, fill=color)
            del img_font
            return img

    def get_italic_angle(
        self,
    ) -> dict[str, Any] | None:
        """
        Gets the font italic angle.

        :returns: The angle value including backslant, italic and roman flags.
        :rtype: dict or None
        """
        font = self.get_ttfont()
        post = font.get("post")
        if not post:
            return None
        italic_angle_value = post.italicAngle
        italic_angle = {
            "backslant": italic_angle_value > 0,
            "italic": italic_angle_value < 0,
            "roman": italic_angle_value == 0,
            "value": italic_angle_value,
        }
        return italic_angle

    @classmethod
    def _get_name_id(
        cls,
        key: int | str,
    ) -> int:
        if isinstance(key, int):
            return key
        elif isinstance(key, str):
            return int(cls._NAMES_BY_KEY[key]["id"])
        else:
            key_type = type(key).__name__
            raise ArgumentError(
                f"Invalid key type, expected int or str, found '{key_type}'."
            )

    def get_name(
        self,
        key: str,
    ) -> str | None:
        """
        Gets the name by its identifier from the font name table.

        :param key: The name id or key (eg. 'family_name')
        :type key: int or str

        :returns: The name.
        :rtype: str or None

        :raises KeyError: if the key is not a valid name key/id
        """
        font = self.get_ttfont()
        name_id = self._get_name_id(key)
        name_table = font["name"]
        name = name_table.getName(name_id, **self._NAMES_MAC_IDS)
        if not name:
            name = name_table.getName(name_id, **self._NAMES_WIN_IDS)
        return str(name.toUnicode()) if name else None

    def get_names(
        self,
    ) -> dict[str, Any]:
        """
        Gets the names records mapped by their property name.

        :returns: The names.
        :rtype: dict
        """
        font = self.get_ttfont()
        names_by_id = {record.nameID: f"{record}" for record in font["name"].names}
        names = {
            self._NAMES_BY_ID[name_id]["key"]: value
            for name_id, value in names_by_id.items()
            if name_id in self._NAMES_BY_ID
        }
        return names

    def get_all_names(
        self,
    ) -> dict[str, list[dict[str, str]]]:
        """
        Gets all the names records mapped by their property name with platform/language info.

        :returns: The names.
        :rtype: dict
        """
        font = self.get_ttfont()
        group_by_name_id = {}
        for record in font["name"].names:
            name_key = self._NAMES_BY_ID.get(record.nameID)
            if not name_key:
                continue
            platform = self._NAME_TABLE_LOOKUP.get(record.platformID)
            encoding = platform.get("encoding").get(record.platEncID)
            language = platform.get("language").get(record.langID)

            full_name = " - ".join(filter(None, [platform.get("name"), encoding, language]))

            group_by_name_id.setdefault(name_key["key"], [])
            group_by_name_id[name_key["key"]].append({
                "name": full_name,
                "platform": platform.get("name"),
                "encoding": encoding,
                "language": language,
                "value": f"{record}",
            })
        return group_by_name_id

    def get_style_flag(
        self,
        key: str,
    ) -> bool:
        """
        Gets the style flag reading OS/2 and macStyle tables.

        :param key: The key
        :type key: string

        :returns: The style flag.
        :rtype: bool
        """
        font = self.get_ttfont()
        bits = self._STYLE_FLAGS[key]
        bit_os2_fs = bits["bit_os2_fs"]
        bit_head_mac = bits["bit_head_mac"]
        # https://docs.microsoft.com/en-us/typography/opentype/spec/os2#fsselection
        flag_os2_fs = False
        if bit_os2_fs is not None:
            os2 = font.get("OS/2")
            if os2:
                flag_os2_fs = get_flag(os2.fsSelection, bit_os2_fs)
        # https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6head.html
        flag_head_mac = False
        if bit_head_mac is not None:
            head = font.get("head")
            if head:
                flag_head_mac = get_flag(head.macStyle, bit_head_mac)
        return flag_os2_fs or flag_head_mac

    def get_style_flags(
        self,
    ) -> dict[str, bool]:
        """
        Gets the style flags reading OS/2 and macStyle tables.

        :returns: The dict representing the style flags.
        :rtype: dict
        """
        return {key: self.get_style_flag(key) for key in self._STYLE_FLAGS_KEYS}

    def get_style_name(
        self,
    ) -> str:
        """
        Gets the style name reading the name records with priority order (17, 22, 2).

        :returns: The font style name.
        :rtype: str
        """
        return (
            self.get_name(self.NAME_TYPOGRAPHIC_SUBFAMILY_NAME)
            or self.get_name(self.NAME_WWS_SUBFAMILY_NAME)
            or self.get_name(self.NAME_SUBFAMILY_NAME)
            or ""
        )

    def get_svg(
        self,
        *,
        text: str,
        size: int,
    ) -> str:
        """
        Gets an SVG representation of the font rendering
        some text using the given options.

        :param text: The text to be rendered as SVG paths.
        :type text: str
        :param size: The size of the font to be used for rendering the text, in points.
        :type size: int

        :returns: An SVG string that represents the rendered text.
        :rtype: str
        """
        font = self.get_ttfont()

        # get font metrics
        units_per_em = font["head"].unitsPerEm
        scale = size / units_per_em
        hhea = font["hhea"]
        ascent = hhea.ascent * scale
        descent = hhea.descent * scale
        width = 0
        height = ascent - descent

        # get glyph set and character map
        glyphset = font.getGlyphSet()
        cmap = font["cmap"].getBestCmap()

        # generate svg path for each glyph in text
        glyphs: list[str] = list(filter(None, [cmap.get(ord(char)) for char in text]))
        paths = ""
        for glyph_name in glyphs:
            glyph = glyphset[glyph_name]
            pen = SVGPathPen(glyphset)
            glyph.draw(pen)
            commands = pen.getCommands()
            transform = f"translate({width:.2f} {ascent:.2f}) scale({scale} -{scale})"
            paths += f"""<path d="{commands}" transform="{transform}" />"""
            width += glyph.width * scale

        # round width and height
        width = int(math.ceil(width))
        height = int(math.ceil(height))
        viewbox = f"0 0 {width} {height}"
        xmlns = "http://www.w3.org/2000/svg"

        # generate svg string
        svg_str = f"""<svg width="{width}" height="{height}" viewBox="{viewbox}" xmlns="{xmlns}">{paths}</svg>"""
        return svg_str

    def get_ttfont(
        self,
    ) -> TTFont:
        """
        Gets the wrapped TTFont instance.

        :returns: The TTFont instance.
        :rtype: TTFont
        """
        return self._ttfont

    @classmethod
    def _populate_unicode_items_set(
        cls,
        items: list[dict[str, Any]],
        items_cache: dict[str, Any],
        item: dict[str, Any],
    ) -> None:
        item_key = item["name"]
        if item_key not in items_cache:
            item = item.copy()
            item["characters_count"] = 0
            items_cache[item_key] = item
            items.append(item)
        item = items_cache[item_key]
        item["characters_count"] += 1

    @staticmethod
    def _get_unicode_items_set_with_coverage(
        all_items: list[dict[str, Any]],
        items: list[dict[str, Any]],
        *,
        coverage_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        all_items = copy.deepcopy(all_items)
        items_indexed = {item["name"]: item.copy() for item in items}
        for item in all_items:
            item_key = item["name"]
            if item_key in items_indexed:
                item["characters_count"] = items_indexed[item_key]["characters_count"]
                item["coverage"] = item["characters_count"] / item["characters_total"]
            else:
                item["characters_count"] = 0
                item["coverage"] = 0.0
        items_filtered = [
            item for item in all_items if item["coverage"] >= coverage_threshold
        ]
        # items_filtered.sort(key=lambda item: item['name'])
        return items_filtered

    def get_unicode_block_by_name(
        self,
        name: str,
    ) -> dict[str, Any] | None:
        """
        Gets the unicode block by name (name is case-insensitive and ignores "-").

        :param name: The name
        :type name: str

        :returns: The unicode block dict if the name is valid, None otherwise.
        :rtype: dict or None
        """
        blocks = self.get_unicode_blocks(coverage_threshold=0.0)
        for block in blocks:
            if slugify(name) == slugify(block["name"]):
                return block
        # raise KeyError("Invalid unicode block name: '{name}'")
        return None

    def get_unicode_blocks(
        self,
        *,
        coverage_threshold: float = 0.00001,
    ) -> list[dict[str, Any]]:
        """
        Gets the unicode blocks and their coverage.
        Only blocks with coverage >= coverage_threshold
        (0.0 <= coverage_threshold <= 1.0) will be returned.

        :param coverage_threshold: The minumum required coverage for a block to be returned.
        :type coverage_threshold: float

        :returns: The list of unicode blocks.
        :rtype: list of dicts
        """
        items: list[dict[str, Any]] = []
        items_cache: dict[str, Any] = {}
        for char in self.get_characters():
            item = {
                "name": char["unicode_block_name"],
            }
            self._populate_unicode_items_set(items, items_cache, item)
        blocks = self._get_unicode_items_set_with_coverage(
            self._UNICODE_BLOCKS, items, coverage_threshold=coverage_threshold
        )
        return blocks

    def get_unicode_script_by_name(
        self,
        name: str,
    ) -> dict[str, Any] | None:
        """
        Gets the unicode script by name/tag (name/tag is case-insensitive and ignores "-").

        :param name: The name
        :type name: str

        :returns: The unicode script dict if the name/tag is valid, None otherwise.
        :rtype: dict or None
        """
        scripts = self.get_unicode_scripts(coverage_threshold=0.0)
        for script in scripts:
            if slugify(name) in (slugify(script["name"]), slugify(script["tag"])):
                return script
        # raise KeyError("Invalid unicode script name/tag: '{name}'")
        return None

    def get_unicode_scripts(
        self,
        *,
        coverage_threshold: float = 0.00001,
    ) -> list[dict[str, Any]]:
        """
        Gets the unicode scripts and their coverage.
        Only scripts with coverage >= coverage_threshold
        (0.0 <= coverage_threshold <= 1.0) will be returned.

        :param coverage_threshold: The minumum required coverage for a script to be returned.
        :type coverage_threshold: float

        :returns: The list of unicode scripts.
        :rtype: list of dicts
        """
        items: list[dict[str, Any]] = []
        items_cache: dict[str, Any] = {}
        for char in self.get_characters():
            item = {
                "name": char["unicode_script_name"],
                "tag": char["unicode_script_tag"],
            }
            self._populate_unicode_items_set(items, items_cache, item)
        scripts = self._get_unicode_items_set_with_coverage(
            self._UNICODE_SCRIPTS, items, coverage_threshold=coverage_threshold
        )
        return scripts

    def get_variable_axes(
        self,
    ) -> list[dict[str, Any]] | None:
        """
        Gets the font variable axes.

        :returns: The list of axes if the font is a variable font otherwise None.
        :rtype: list of dict or None
        """
        if not self.is_variable():
            return None
        font = self.get_ttfont()
        return [
            {
                "tag": axis.axisTag,
                "name": self._VARIABLE_AXES_BY_TAG.get(axis.axisTag, {}).get(
                    "name", axis.axisTag.title()
                ),
                "min_value": axis.minValue,
                "max_value": axis.maxValue,
                "default_value": axis.defaultValue,
            }
            for axis in font["fvar"].axes
        ]

    def get_variable_axis_by_tag(
        self,
        tag: str,
    ) -> dict[str, Any] | None:
        """
        Gets a variable axis by tag.

        :param tag: The tag
        :type tag: string

        :returns: The variable axis by tag.
        :rtype: dict or None
        """
        axes = self.get_variable_axes()
        if axes:
            for axis in axes:
                if axis.get("tag") == tag:
                    return axis
        # raise KeyError("Invalid axis tag: '{tag}'")
        return None

    def get_variable_axes_tags(
        self,
    ) -> list[str] | None:
        """
        Gets the variable axes tags.

        :returns: The variable axis tags.
        :rtype: list or None
        """
        if not self.is_variable():
            return None
        font = self.get_ttfont()
        return [axis.axisTag for axis in font["fvar"].axes]

    def get_variable_instances(
        self,
    ) -> list[dict[str, Any]] | None:
        """
        Gets the variable instances.

        :returns: The list of instances if the font is a variable font otherwise None.
        :rtype: list of dict or None
        """
        if not self.is_variable():
            return None
        font = self.get_ttfont()
        name_table = font["name"]
        return [
            {
                "coordinates": instance.coordinates,
                "style_name": name_table.getDebugName(instance.subfamilyNameID),
            }
            for instance in font["fvar"].instances
        ]

    def get_variable_instance_by_style_name(
        self,
        style_name: str,
    ) -> dict[str, Any] | None:
        """
        Gets the variable instance by style name, eg. style_name = 'Bold'

        :param style_name: The style name
        :type style_name: str

        :returns: The variable instance matching the given style name.
        :rtype: dict or None
        """
        instances = self.get_variable_instances() or []
        for instance in instances:
            if slugify(instance["style_name"]) == slugify(style_name):
                return instance
        return None

    def get_variable_instance_closest_to_coordinates(
        self,
        coordinates: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Gets the variable instance closest to coordinates.
        eg. coordinates = {'wght': 1000, 'slnt': 815, 'wdth': 775}
        If coordinates do not specify some axes, axes default value is used for lookup.

        :param coordinates: The coordinates
        :type coordinates: dict

        :returns: The variable instance closest to coordinates.
        :rtype: dict or None
        """
        if not self.is_variable():
            return None

        # set default axes values for axes not present in coordinates
        lookup_values = coordinates.copy()
        axes = self.get_variable_axes() or []
        for axis in axes:
            # don't use setdefault to override possible None values
            if lookup_values.get(axis["tag"]) is None:
                lookup_values[axis["tag"]] = axis["default_value"]

        instances = self.get_variable_instances() or []
        closest_instance_distance = float(sys.maxsize)
        closest_instance = None
        for instance in instances:
            instance_values = instance["coordinates"]
            instance_distance = get_euclidean_distance(instance_values, lookup_values)
            if instance_distance < closest_instance_distance:
                closest_instance_distance = instance_distance
                closest_instance = instance
        return closest_instance

    def get_version(
        self,
    ) -> float:
        """
        Gets the font version.

        :returns: The font version value.
        :rtype: float
        """
        font = self.get_ttfont()
        head = font.get("head")
        version = float(head.fontRevision)
        return version

    def get_vertical_metrics(
        self,
    ) -> dict[str, Any]:
        """
        Gets the font vertical metrics.

        :returns: A dictionary containing the following vertical metrics:
            "units_per_em", "y_max", "y_min", "ascent", "descent", "line_gap",
            "typo_ascender", "typo_descender", "typo_line_gap", "cap_height", "x_height",
            "win_ascent", "win_descent"
        :rtype: dict
        """
        font = self.get_ttfont()
        metrics = {}
        for metric in self._VERTICAL_METRICS:
            table = font.get(metric["table"])
            metrics[metric["key"]] = (
                getattr(table, metric["attr"], None) if table else None
            )
        return metrics

    def get_weight(
        self,
    ) -> dict[str, Any] | None:
        """
        Gets the font weight value and name.

        :returns: The weight name and value.
        :rtype: dict or None
        """
        font = self.get_ttfont()
        os2 = font.get("OS/2")
        if not os2:
            return None
        weight_value = os2.usWeightClass
        weight_value = min(max(1, weight_value), 1000)
        weight_option_values = sorted(self._WEIGHTS_BY_VALUE.keys())
        closest_weight_option_value = min(
            weight_option_values,
            key=lambda weight_option_value: abs(weight_option_value - weight_value),
        )
        weight = self._WEIGHTS_BY_VALUE.get(closest_weight_option_value, {}).copy()
        weight["value"] = weight_value
        return weight

    def get_glyph_proportions(
        self,
        glpyhs="oO"
    ) -> float | None:
        """
        Gets the proportion of the glyph in the font. (Based on the bounding box)

        :param glpyhs: The first available glyph will be checked.
        :type glpyhs: str
        :returns: The proportion of the glyph.
        :rtype: float or None
        """
        font = self.get_ttfont()
        glyphset = font.getGlyphSet()
        for glyph_name in glpyhs:
            glyph_to_check = glyphset.get(glyph_name)
            if glyph_to_check:
                continue
        if not glyph_to_check:
            return None

        bp = BoundsPen(glyphset)
        glyph_to_check.draw(bp)

        x = bp.bounds[2] - bp.bounds[0]
        y = bp.bounds[3] - bp.bounds[1]
        return x / y

    def get_glyph_weight(
        self,
        glpyhs="oO"
    ) -> float | None:
        """
        Gets the weight of the glyph in the font. (Percentage of the glyph that is filled)

        :param glpyhs: The first available glyph will be checked.
        :type glpyhs: str
        :returns: The proportion of the glyph.
        :rtype: float or None
        """
        font = self.get_ttfont()
        glyphset = font.getGlyphSet()
        for glyph_name in glpyhs:
            glyph_to_check = glyphset.get(glyph_name)
            if glyph_to_check:
                continue
        if not glyph_to_check:
            return None

        bp = BoundsPen(glyphset)
        glyph_to_check.draw(bp)

        x = bp.bounds[2] - bp.bounds[0]
        y = bp.bounds[3] - bp.bounds[1]
        full_area = x * y

        ap = AreaPen(glyphset)
        glyph_to_check.draw(ap)
        area = abs(ap.value)
        return area / full_area

    def get_width(
        self,
    ) -> dict[str, Any] | None:
        """
        Gets the font width value and name.

        :returns: The width name and value.
        :rtype: dict or None
        """
        font = self.get_ttfont()
        os2 = font.get("OS/2")
        if not os2:
            return None
        width_value = os2.usWidthClass
        width_value = min(max(1, width_value), 9)
        width = self._WIDTHS_BY_VALUE.get(width_value, {}).copy()
        width["value"] = width_value
        return width

    def is_color(
        self,
    ) -> bool:
        """
        Determines if the font is a color font.

        :returns: True if color font, False otherwise.
        :rtype: bool
        """
        font = self.get_ttfont()
        tables = {"COLR", "CPAL", "CBDT", "CBLC"}
        for table in tables:
            if table in font:
                return True
        return False

    def is_monospace(
        self,
        threshold: float = 0.85,
    ) -> bool:
        """
        Determines if the font is a monospace font.

        :param threshold: The threshold (0.0 <= n <= 1.0) of glyphs with the same width to consider the font as monospace.
        :type threshold: float

        :returns: True if monospace font, False otherwise.
        :rtype: bool
        """
        font = self.get_ttfont()
        widths = [metrics[0] for metrics in font["hmtx"].metrics.values()]
        widths_counter = Counter(widths)
        same_width_count = widths_counter.most_common(1)[0][1]
        same_width_amount = same_width_count / self.get_glyphs_count()
        return same_width_amount >= threshold

    def is_all_caps(self):
        font = self.get_ttfont()
        glyf_table = font["glyf"]
        def normalize_glyphs(glyph_name):
            coordinates = glyf_table[glyph_name].getCoordinates(glyf_table)[0]
            return [(x[0] - coordinates[0][0], x[1] - coordinates[0][1]) for x in coordinates]
        for letter in string.ascii_lowercase:
            # Still has false negatives when the path is slightly different
            if normalize_glyphs(font, letter) != normalize_glyphs(font, letter.upper()):
                return False
        return True

    def is_static(
        self,
    ) -> bool:
        """
        Determines if the font is a static font.

        :returns: True if static font, False otherwise.
        :rtype: bool
        """
        return not self.is_variable()

    def is_variable(
        self,
    ) -> bool:
        """
        Determines if the font is a variable font.

        :returns: True if variable font, False otherwise.
        :rtype: bool
        """
        font = self.get_ttfont()
        return "fvar" in font

    def rename(
        self,
        *,
        family_name: str = "",
        style_name: str = "",
        update_style_flags: bool = True,
    ) -> None:
        """
        Renames the font names records (1, 2, 4, 6, 16, 17) according to
        the given family_name and style_name (subfamily_name).

        If family_name is not defined it will be auto-detected.
        If style_name is not defined it will be auto-detected.

        :param family_name: The family name
        :type family_name: str
        :param style_name: The style name
        :type style_name: str
        :param update_style_flags: if True the style flags will be updated by subfamily name
        :type update_style_flags: bool

        :raises ValueError: if the computed PostScript-name is longer than 63 characters.
        :return: None
        """
        family_name = (family_name or "").strip() or self.get_family_name()
        style_name = (style_name or "").strip() or self.get_style_name()

        # typographic and wws names
        typographic_family_name = family_name
        typographic_subfamily_name = style_name
        wws_family_name = family_name
        wws_subfamily_name = style_name

        # family name and subfamily name
        subfamily_names = ["regular", "italic", "bold", "bold italic"]
        subfamily_name = style_name.lower()
        if subfamily_name not in subfamily_names:
            # fix legacy name records 1 and 2
            family_name_suffix = re.sub(
                r"\ italic$", "", style_name, flags=re.IGNORECASE
            )
            if family_name_suffix:
                family_name = f"{typographic_family_name} {family_name_suffix}"
            subfamily_name = subfamily_names["italic" in subfamily_name]
        subfamily_name = subfamily_name.title()

        # full name
        full_name = concat_names(typographic_family_name, typographic_subfamily_name)

        # postscript name
        postscript_name = concat_names(
            remove_spaces(typographic_family_name),
            remove_spaces(typographic_subfamily_name),
        )

        # keep only printable ASCII subset:
        # https://learn.microsoft.com/en-us/typography/opentype/spec/name#name-ids
        # postscript_name_allowed_chars = {chr(code) for code in range(33, 127)}
        # !"#$&'*+,-.0123456789:;=?@ABCDEFGHIJKLMNOPQRSTUVWXYZ\^_`abcdefghijklmnopqrstuvwxyz|~
        postscript_name_pattern = (
            r"[^0-9A-Za-z\!\"\#\$\&\'\*\+\,\-\.\:\;\=\?\@\\\^\_\`\|\~]"
        )
        postscript_name = re.sub(postscript_name_pattern, "-", postscript_name)
        postscript_name = re.sub(r"[\-]+", "-", postscript_name).strip("-")
        postscript_name_length = len(postscript_name)
        if postscript_name_length > 63:
            raise ArgumentError(
                "Computed PostScript name exceeded 63 characters max-length"
                f" ({postscript_name_length} characters)."
            )

        # update unique identifier
        postscript_name_old = self.get_name(self.NAME_POSTSCRIPT_NAME) or ""
        unique_identifier = self.get_name(self.NAME_UNIQUE_IDENTIFIER) or ""
        unique_identifier = unique_identifier.replace(
            postscript_name_old,
            postscript_name,
        )

        # update name records
        names = {
            self.NAME_FAMILY_NAME: family_name,
            self.NAME_SUBFAMILY_NAME: subfamily_name,
            self.NAME_UNIQUE_IDENTIFIER: unique_identifier,
            self.NAME_FULL_NAME: full_name,
            self.NAME_POSTSCRIPT_NAME: postscript_name,
            self.NAME_TYPOGRAPHIC_FAMILY_NAME: typographic_family_name,
            self.NAME_TYPOGRAPHIC_SUBFAMILY_NAME: typographic_subfamily_name,
            self.NAME_WWS_FAMILY_NAME: wws_family_name,
            self.NAME_WWS_SUBFAMILY_NAME: wws_subfamily_name,
        }
        self.set_names(names=names)

        if update_style_flags:
            self.set_style_flags_by_subfamily_name()

    def sanitize(
        self,
        *,
        strict: bool = True,
    ) -> None:
        """
        Sanitize the font file using OpenType Sanitizer.
        https://github.com/googlefonts/ots-python

        :param strict: If True (default), raises an exception even on sanitizer warnings.
            If False, only raises an exception on sanitizer failure (non-zero exit code).
        :type strict: bool

        :raises Exception: If the OpenType Sanitizer reports an error during the sanitization process.
        :return: None

        :note: Uses OpenType Sanitizer (ots) to sanitize the font file.
            Saves the font to a temporary directory and invokes the sanitizer on the saved file.
            If `strict` is True (default), treats sanitizer warnings as errors.
            If `strict` is False, only checks for sanitizer errors.
        """
        with tempfile.TemporaryDirectory() as dest:
            filename = self.get_filename()
            filepath = fsutil.join_path(dest, filename)
            filepath = self.save(filepath)
            result = ots.sanitize(
                filepath,
                capture_output=True,
                encoding="utf-8",
            )
            error_code = result.returncode
            errors = result.stderr
            if error_code:
                raise SanitizationError(
                    f"OpenType Sanitizer returned non-zero exit code ({error_code}): \n{errors}"
                )

            elif strict:
                warnings = result.stdout
                success_message = "File sanitized successfully!\n"
                if warnings != success_message:
                    warnings = warnings.rstrip(success_message)
                    raise SanitizationError(
                        f"OpenType Sanitizer warnings: \n{warnings}"
                    )

    def save(
        self,
        filepath: str | Path | None = None,
        *,
        overwrite: bool = False,
    ) -> str:
        """
        Saves the font at filepath.

        :param filepath: The filepath, if None the source filepath will be used
        :type filepath: str or None
        :param overwrite: The overwrite, if True the source font file can be overwritten
        :type overwrite: bool

        :returns: The filepath where the font has been saved to.
        :rtype: str

        :raises ValueError: If the filepath is the same of the source font
        and overwrite is not allowed.

        :raises ValueError: If the font was created from a file object, and filepath is
        not specififed.
        """
        if not filepath and not self._filepath:
            raise ArgumentError(
                "Font doesn't have a filepath. Please specify a filepath to save to."
            )

        if filepath is None:
            filepath = self._filepath

        filepath = str(filepath)
        filepath_is_dir = fsutil.is_dir(filepath) or filepath.endswith(os.sep)
        filepath_is_font_file = (
            fsutil.get_file_extension(filepath) in self._FORMATS_LIST
        )
        if filepath_is_dir or not filepath_is_font_file:
            dirpath = filepath
            basename = fsutil.get_file_basename(self.get_filename())
            extension = ""
        else:
            dirpath, filename = fsutil.split_filepath(filepath)
            basename, extension = fsutil.split_filename(filename)

        format_ = self.get_format()
        extension = format_
        filename = fsutil.join_filename(basename, extension)
        filepath = fsutil.join_filepath(dirpath, filename)
        filepath = str(filepath)
        if fsutil.is_file(filepath) and not overwrite:
            raise ArgumentError(
                f"Invalid filepath, a file already exists at '{filepath}' "
                "and 'overwrite' option is 'False' (consider using 'overwrite=True')."
            )
        fsutil.make_dirs_for_file(filepath)

        font = self.get_ttfont()
        font.save(filepath)
        return filepath

    def _save_with_flavor(
        self,
        *,
        flavor: str,
        filepath: str | Path | None = None,
        overwrite: bool = True,
    ) -> str:
        font = self.get_ttfont()
        presave_flavor = font.flavor
        font.flavor = flavor
        # save
        saved_font_filepath = self.save(
            filepath=filepath,
            overwrite=overwrite,
        )
        # revert changes
        font.flavor = presave_flavor
        # return file path
        return saved_font_filepath

    def save_as_woff(
        self,
        filepath: str | Path | None = None,
        *,
        overwrite: bool = True,
    ) -> str:
        """
        Saves font as woff.

        :param filepath: The filepath
        :type filepath: str
        :param overwrite: The overwrite, if True the source font file can be overwritten
        :type overwrite: bool

        :returns: The filepath where the font has been saved to.
        :rtype: str
        """
        return self._save_with_flavor(
            flavor=self.FORMAT_WOFF,
            filepath=filepath,
            overwrite=overwrite,
        )

    def save_as_woff2(
        self,
        filepath: str | Path | None = None,
        *,
        overwrite: bool = True,
    ) -> str:
        """
        Saves font as woff2.

        :param filepath: The filepath
        :type filepath: str
        :param overwrite: The overwrite, if True the source font file can be overwritten
        :type overwrite: bool

        :returns: The filepath where the font has been saved to.
        :rtype: str
        """
        return self._save_with_flavor(
            flavor=self.FORMAT_WOFF2,
            filepath=filepath,
            overwrite=overwrite,
        )

    def save_to_fileobject(
        self,
        fileobject: IO | None = None,
    ) -> IO:
        """
        Writes the font to a file-like object. If no file-object is passed, an
        instance of `BytesIO` is created for the user.
        :param fileobject: A file-like object to write to.

        :returns: The file object that was originally pass, or a new BytesIO
        instance.
        :rtype: typing.io.IO
        """
        font = self.get_ttfont()
        if fileobject is None:
            fileobject = BytesIO()
        font.save(fileobject)
        return fileobject

    def save_variable_instances(
        self,
        dirpath: str | Path,
        *,
        woff2: bool = True,
        woff: bool = True,
        overwrite: bool = True,
        **options: Any,
    ) -> list[dict[str, Any]]:
        """
        Save all instances of a variable font to specified directory in one or more format(s).

        :param dirpath: The dirpath
        :type dirpath: The directory path where the instances will be saved.
        :param woff2: Whether to save instances also in WOFF2 format. Default is True.
        :type woff2: bool
        :param woff: Whether to save instances also in WOFF format. Default is True.
        :type woff: bool
        :param overwrite: Whether to overwrite existing files in the directory. Default is True.
        :type overwrite: bool
        :param options: Additional options to be passed to the instancer when generating static instances.
        :type options: dictionary

        :returns: A list containing dictionaries for each saved instance. Each dictionary
            includes 'instance' (containing instance metadata) and 'files' (a dictionary
            with file formats as keys and file-paths as values).

        :raises TypeError: If the font is not a variable font.
        """
        if not self.is_variable():
            raise OperationError("Only a variable font can be instantiated.")

        fsutil.assert_not_file(dirpath)
        fsutil.make_dirs(dirpath)

        instances_format = self.get_format()
        instances_saved = []
        instances = self.get_variable_instances() or []
        for instance in instances:
            # make instance
            instance_font = self.clone()
            instance_font.to_static(
                coordinates=instance["coordinates"],
                **options,
            )
            instance_font.rename(
                style_name=instance["style_name"],
            )
            instance_files: dict[str, Any] = {
                Font.FORMAT_OTF: None,
                Font.FORMAT_TTF: None,
                Font.FORMAT_WOFF2: None,
                Font.FORMAT_WOFF: None,
            }
            instance_files[instances_format] = instance_font.save(
                dirpath,
                overwrite=overwrite,
            )
            if woff2 and not instance_files[Font.FORMAT_WOFF2]:
                instance_files[Font.FORMAT_WOFF2] = instance_font.save_as_woff2(
                    dirpath,
                    overwrite=overwrite,
                )
            if woff and not instance_files[Font.FORMAT_WOFF]:
                instance_files[Font.FORMAT_WOFF] = instance_font.save_as_woff(
                    dirpath,
                    overwrite=overwrite,
                )
            instance_saved = {}
            instance_saved["files"] = instance_files.copy()
            instance_saved["instance"] = instance.copy()
            instances_saved.append(instance_saved)
        return instances_saved

    def set_family_classification(
        self,
        class_id: int,
        subclass_id: int = 0,
    ) -> None:
        """
        Sets font family classification (sFamilyClass in the OS/2 table)
        based on provided class_id and subclass_id.

        :param class_id: Numeric identifier of the font family class.
        :param subclass_id: Optional numeric identifier of the font family subclass (default is 0).
        :raises OperationError: If the OS/2 table is not available in the font.
        :raises ArgumentError: If class_id is invalid or subclass_id is specified but invalid.
        """
        font = self.get_ttfont()
        os2 = font.get("OS/2")
        if not os2:
            raise OperationError("Invalid OS/2 table (doesn't exist).")

        # validate class key and subclass key
        class_item, subclass_item = self._get_family_classification_items(
            class_id=class_id,
            subclass_id=subclass_id,
        )
        if not class_item:
            raise ArgumentError("Invalid class key argument.")

        if not subclass_item and subclass_id:
            raise ArgumentError("Invalid subclass key argument.")

        class_id = class_item["id"]
        if subclass_item:
            subclass_id = subclass_item["id"]

        family_class = (class_id << 8) | (subclass_id & 0xFF)
        os2.sFamilyClass = family_class

    def set_family_name(
        self,
        name: str,
    ) -> None:
        """
        Sets the family name updating the related font names records.

        :param name: The name
        :type name: The new family name.
        """
        self.rename(
            family_name=name,
            style_name=self.get_style_name(),
        )

    def set_name(
        self,
        key: int | str,
        value: str,
    ) -> None:
        """
        Sets the name by its identifier in the font name table.

        :param key: The name id or key (eg. 'family_name')
        :type key: int or str
        :param value: The value
        :type value: str
        """
        font = self.get_ttfont()
        name_id = self._get_name_id(key)
        name_table = font["name"]
        # https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/ttLib/tables/_n_a_m_e.py#L568
        name_table.setName(value, name_id, **self._NAMES_MAC_IDS)
        name_table.setName(value, name_id, **self._NAMES_WIN_IDS)

    def set_names(
        self,
        names: dict[str, str],
    ) -> None:
        """
        Sets the names by their identifier in the name table.

        :param names: The names
        :type names: dict
        """
        for key, value in names.items():
            self.set_name(key, value)

    def set_style_flag(
        self,
        key: str,
        value: bool,
    ) -> None:
        """
        Sets the style flag.

        :param key: The flag key
        :type key: str
        :param value: The value
        :type value: bool
        """
        font = self.get_ttfont()
        bits = self._STYLE_FLAGS[key]
        bit_os2_fs = bits["bit_os2_fs"]
        bit_head_mac = bits["bit_head_mac"]
        if bit_os2_fs is not None:
            os2 = font.get("OS/2")
            if os2:
                os2.fsSelection = set_flag(os2.fsSelection, bit_os2_fs, value)
        if bit_head_mac is not None:
            head = font.get("head")
            if head:
                head.macStyle = set_flag(head.macStyle, bit_head_mac, value)

    def set_style_flags(
        self,
        *,
        regular: bool | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
        outline: bool | None = None,
        shadow: bool | None = None,
        condensed: bool | None = None,
        extended: bool | None = None,
    ) -> None:
        """
        Sets the style flags, keys set to None will be ignored.

        :param regular: The regular style flag value
        :type regular: bool or None
        :param bold: The bold style flag value
        :type bold: bool or None
        :param italic: The italic style flag value
        :type italic: bool or None
        :param underline: The underline style flag value
        :type underline: bool or None
        :param outline: The outline style flag value
        :type outline: bool or None
        :param shadow: The shadow style flag value
        :type shadow: bool or None
        :param condensed: The condensed style flag value
        :type condensed: bool or None
        :param extended: The extended style flag value
        :type extended: bool or None
        """
        flags = locals()
        flags.pop("self")
        for key, value in flags.items():
            if value is not None:
                assert isinstance(value, bool)
                self.set_style_flag(key, value)

    def set_style_flags_by_subfamily_name(
        self,
    ) -> None:
        """
        Sets the style flags by the subfamily name value.
        The subfamily values should be "regular", "italic", "bold" or "bold italic"
        to allow this method to work properly.
        """
        subfamily_name = (self.get_name(Font.NAME_SUBFAMILY_NAME) or "").lower()
        if subfamily_name == Font.STYLE_FLAG_REGULAR:
            self.set_style_flags(regular=True, bold=False, italic=False)
        elif subfamily_name == Font.STYLE_FLAG_BOLD:
            self.set_style_flags(regular=False, bold=True, italic=False)
        elif subfamily_name == Font.STYLE_FLAG_ITALIC:
            self.set_style_flags(regular=False, bold=False, italic=True)
        elif subfamily_name == f"{Font.STYLE_FLAG_BOLD} {Font.STYLE_FLAG_ITALIC}":
            self.set_style_flags(regular=False, bold=True, italic=True)

    def set_style_name(
        self,
        name: str,
    ) -> None:
        """
        Sets the style name updating the related font names records.

        :param name: The new style name
        :type name: str.
        """
        self.rename(
            family_name=self.get_family_name(),
            style_name=name,
        )

    def set_vertical_metrics(
        self,
        **metrics: Any,
    ) -> None:
        """
        Sets the vertical metrics.

        :param metrics: Keyword arguments representing the vertical metrics that can be set:
            "units_per_em", "y_max", "y_min", "ascent", "descent", "line_gap",
            "typo_ascender", "typo_descender", "typo_line_gap", "cap_height", "x_height",
            "win_ascent", "win_descent"
        """
        font = self.get_ttfont()
        for metric in self._VERTICAL_METRICS:
            if metric["key"] in metrics:
                table = font.get(metric["table"])
                if table:
                    setattr(table, metric["attr"], metrics[metric["key"]])

    def subset(
        self,
        *,
        unicodes: list[str | int] | str = "",
        glyphs: list[str] | None = None,
        text: str = "",
        **options: Any,
    ) -> None:
        """
        Subsets the font using the given options (unicodes or glyphs or text),
        it is possible to pass also subsetter options, more info here:
        https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/subset/__init__.py

        :param unicodes: The unicodes
        :type unicodes: str or list
        :param glyphs: The glyphs
        :type glyphs: list
        :param text: The text
        :type text: str
        :param options: The subsetter options
        :type options: dict
        """
        font = self.get_ttfont()
        if not any([unicodes, glyphs, text]):
            raise ArgumentError(
                "Subsetting requires at least one of "
                "the following args: unicode, glyphs, text."
            )
        unicodes_list = parse_unicodes(unicodes)
        glyphs_list = glyphs or []
        options.setdefault("glyph_names", True)
        options.setdefault("ignore_missing_glyphs", True)
        options.setdefault("ignore_missing_unicodes", True)
        options.setdefault("layout_features", ["*"])
        options.setdefault("name_IDs", "*")
        options.setdefault("notdef_outline", True)
        subs_args = {
            "unicodes": unicodes_list,
            "glyphs": glyphs_list,
            "text": text,
        }
        # https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/subset/__init__.py
        subs_options = SubsetterOptions(**options)
        subs = Subsetter(options=subs_options)
        subs.populate(**subs_args)
        subs.subset(font)

    @staticmethod
    def _all_axes_pinned(
        axes: dict[str, Any],
    ) -> bool:
        """
        Check if all the axes values are pinned or not.

        :param axes: The axes
        :type axes: dict
        :returns: True if all the axes values are pinned, False otherwise.
        :rtype: bool
        """
        return all(
            isinstance(axis_value, (type(None), int, float))
            for axis_value in axes.values()
        )

    def to_sliced_variable(
        self,
        *,
        coordinates: dict[str, Any],
        **options: Any,
    ) -> None:
        """
        Converts the variable font to a partial one slicing
        the variable axes at the given coordinates.
        If an axis value is not specified, the axis will be left untouched.
        If an axis min and max values are equal, the axis will be pinned.

        :param coordinates: The coordinates dictionary, each item value must be tuple/list/dict
            (with 'min', 'default' and 'max' keys) for slicing or float/int for pinning, eg.
            {'wdth':100, 'wght':(100,600), 'ital':(30,65,70)} or
            {'wdth':100, 'wght':[100,600], 'ital':[30,65,70]} or
            {'wdth':100, 'wght':{'min':100,'max':600}, 'ital':{'min':30,'default':65,'max':70}}
        :type coordinates: dict
        :param options: The options for the fontTools.varLib.instancer
        :type options: dictionary

        :raises TypeError: If the font is not a variable font
        :raises ValueError: If the coordinates are not defined (blank)
        :raises ValueError: If the coordinates axes are all pinned
        """
        if not self.is_variable():
            raise OperationError("Only a variable font can be sliced.")

        font = self.get_ttfont()
        coordinates = coordinates or {}
        coordinates_axes_tags = coordinates.keys()

        # make coordinates more friendly accepting also list and dict values
        for axis_tag in coordinates_axes_tags:
            axis_value = coordinates[axis_tag]
            if isinstance(axis_value, list):
                axis_value = tuple(axis_value)
            elif isinstance(axis_value, dict):
                axis = self.get_variable_axis_by_tag(axis_tag) or {}
                axis_min = axis_value.get("min", axis.get("min_value"))
                axis_default = axis_value.get("default", axis.get("default_value"))
                axis_max = axis_value.get("max", axis.get("max_value"))
                axis_value = (axis_min, axis_default, axis_max)
            coordinates[axis_tag] = axis_value

        # ensure that coordinates axes are defined and that are not all pinned
        if len(coordinates_axes_tags) == 0:
            raise ArgumentError("Invalid coordinates: axes not defined.")
        elif set(coordinates_axes_tags) == set(self.get_variable_axes_tags() or []):
            if self._all_axes_pinned(coordinates):
                raise ArgumentError(
                    "Invalid coordinates: all axes are pinned (use to_static method)."
                )

        # set default instancer options
        options.setdefault("optimize", True)
        options.setdefault("overlap", OverlapMode.KEEP_AND_SET_FLAGS)
        options.setdefault("updateFontNames", False)

        # instantiate the sliced variable font
        instancer.instantiateVariableFont(font, coordinates, inplace=True, **options)

    def to_static(
        self,
        *,
        coordinates: dict[str, Any] | None = None,
        style_name: str | None = None,
        update_names: bool = True,
        update_style_flags: bool = True,
        **options: Any,
    ) -> None:
        """
        Converts the variable font to a static one pinning
        the variable axes at the given coordinates.
        If an axis value is not specified, the axis will be pinned at its default value.
        If coordinates are not specified each axis will be pinned at its default value.

        :param coordinates: The coordinates, eg. {'wght':500, 'ital':50}
        :type coordinates: dict or None
        :param style_name: The existing instance style name, eg. 'Black'
        :type style_name: str or None
        :param update_names: if True the name records will be updated based on closest instance
        :type update_names: bool
        :param update_style_flags: if True the style flags will be updated based on closest instance
        :type update_style_flags: bool

        :param options: The options for the fontTools.varLib.instancer
        :type options: dictionary

        :raises TypeError: If the font is not a variable font
        :raises ValueError: If the coordinates axes are not all pinned
        """
        if not self.is_variable():
            raise OperationError("Only a variable font can be made static.")

        font = self.get_ttfont()

        # take coordinates from instance with specified style name
        if style_name:
            if coordinates:
                raise ArgumentError(
                    "Invalid arguments: 'coordinates' and 'style_name' are mutually exclusive."
                )
            instance = self.get_variable_instance_by_style_name(style_name=style_name)
            if not instance:
                raise ArgumentError(
                    f"Invalid style name: instance with style name '{style_name}' not found."
                )
            coordinates = instance["coordinates"].copy()

        # make coordinates more friendly by using default axis values by default
        coordinates = coordinates or {}
        default_coordinates = {
            axis_tag: None
            for axis_tag in (self.get_variable_axes_tags() or [])
            if axis_tag not in coordinates
        }
        coordinates.update(default_coordinates)

        # ensure that coordinates axes are all pinned
        if not self._all_axes_pinned(coordinates):
            raise ArgumentError("Invalid coordinates: all axes must be pinned.")

        # get instance closest to coordinates
        instance = self.get_variable_instance_closest_to_coordinates(coordinates)

        # set default instancer options
        options["inplace"] = True
        options.setdefault("optimize", True)
        options.setdefault("overlap", OverlapMode.REMOVE)
        options.setdefault("updateFontNames", False)

        # instantiate the static font
        instancer.instantiateVariableFont(font, coordinates, **options)

        # update name records and style flags based on instance style name
        if instance and update_names:
            self.rename(
                style_name=instance["style_name"],
                update_style_flags=update_style_flags,
            )

        # update style flags based on coordinates values
        if update_style_flags:
            has_italic = (coordinates.get("ital", 0) or 0) == 1
            has_slant = (coordinates.get("slnt", 0) or 0) < 0
            if has_italic or has_slant:
                self.set_style_flags(regular=False, italic=True)

    def __str__(
        self,
    ) -> str:
        """
        Returns a string representation of the object.

        :returns: String representation of the object.
        :rtype: str
        """
        return f"{type(self).__name__}('{self._filepath}')"
