# Test tree: spoken suffix after the name (DD-39, task SUF-RED)

The voice says "<name> <suffix>", for example "राजेश कुमार जी". The suffix is set by
`Settings.spoken_suffix` (env `VIDGEN_SPOKEN_SUFFIX`, default "जी", max 20 characters, "" switches
it off) and reaches the row pipeline through `RenderConfig.spoken_suffix` (default ""). The
text is built by the pure function `spoken_text(name, suffix)`. The suffix is not added when the
last word of the name already equals it (case-insensitive). A confirmed spoken name (DD-38, D3)
is the base for the suffix.

```
Feature: spoken suffix after the name (DD-39)
├── Scenario: the pure text rule  (tests/unit/services/test_spoken_text.py)
│   ├── ✅ SS-F-P1 Roman name: "Asha Verma" -> "Asha Verma जी"
│   ├── ✅ SS-F-P2 Devanagari name gets the Devanagari suffix after one space
│   ├── ✅ SS-F-P3 title kept in front: "Smt. Asha Verma" -> "Smt. Asha Verma जी"
│   ├── ✅ SS-F-P4 single-word name: "Asha" -> "Asha जी"
│   ├── ✅ SS-F-P5 Roman suffix "Ji" is added as typed
│   ├── ❌ SS-F-N1 empty suffix -> name unchanged (feature off)
│   ├── ❌ SS-F-N2 suffix of only spaces counts as empty
│   ├── ❌ SS-F-N3 name ends with the suffix -> not doubled ("Asha जी" + "जी")
│   ├── ❌ SS-F-N4 Roman last word equal in any case ("Asha ji" + "Ji", "JI", "ji")
│   ├── ❌ SS-F-N5 a MIDDLE word equal to the suffix does not stop the suffix
│   ├── ❌ SS-F-N6 name that only ends with the letters ("Amitजी", "Amitji") gets the suffix
│   ├── ⚠️ SS-F-E1 spaces, tabs and newlines around both arguments are stripped
│   ├── ⚠️ SS-F-E2 trailing spaces in the name give exactly one space before the suffix
│   ├── ⚠️ SS-F-E3 empty or blank name -> "" (never the suffix alone); both empty -> ""
│   ├── ⚠️ SS-F-E4 name equal to the suffix is returned unchanged
│   ├── ⚠️ SS-F-E5 ZWJ and ZWNJ inside the name are kept; a joiner at the end is not the suffix
│   ├── ⚠️ SS-F-E6 emoji and right-to-left letters pass through; suffix last
│   ├── ⚠️ SS-F-E7 forty-grapheme name still gets the suffix
│   └── ⚠️ SS-F-E8 applying the function twice adds the suffix once (stable output)
├── Scenario: the Admin sets the suffix  (tests/unit/infra/test_spoken_suffix_setting.py)
│   ├── ✅ SS-S-P1 default "जी" when the variable is not set
│   ├── ✅ SS-S-P2 VIDGEN_SPOKEN_SUFFIX overrides it (Devanagari or Roman)
│   ├── ✅ SS-S-P3 render_config copies the default and a changed value
│   ├── ✅ SS-S-P4 RenderConfig built without the field has spoken_suffix ""
│   ├── ❌ SS-S-N1 21 characters rejected (ValidationError naming spoken_suffix), also from env
│   ├── ⚠️ SS-S-E1 empty value allowed, kept as "", copied to the render config
│   └── ⚠️ SS-S-E2 exactly 20 characters accepted (boundary); 19 accepted
├── Scenario: a batch row speaks the suffix  (tests/integration/worker/test_render_row_spoken_suffix.py)
│   ├── ✅ SS-R-P1 config "जी": voice gets "<name> जी" (Roman and Devanagari names)
│   ├── ✅ SS-R-P2 confirmed spoken name (D3) is spoken with the suffix after it
│   ├── ❌ SS-R-N1 no suffix configured (default): voice gets the name only
│   ├── ⚠️ SS-R-E1 name already ending with the suffix ("Asha जी"; "Asha ji" with "Ji") is not doubled
│   ├── ⚠️ SS-R-E2 suffix word in the middle of the name does not stop the suffix
│   ├── ⚠️ SS-R-E3 the ID is never spoken, also with a suffix (R3.3)
│   └── ⚠️ SS-R-E4 spoken name already ending with the suffix is spoken once
└── Scenario: the preview speaks the suffix  (tests/integration/worker/test_render_row_spoken_suffix.py)
    ├── ✅ SS-P-P1 no confirmation: preview gets "Asha Verma जी"
    ├── ✅ SS-P-P2 confirmed spelling "आशा वर्मा" gets the suffix: "आशा वर्मा जी"
    ├── ❌ SS-P-N1 suffix "" (off): preview gets the confirmed name only
    └── ⚠️ SS-P-E1 confirmed spelling already ending with the suffix is spoken once
```

Coverage map to the DD-39 contract: `spoken_text` rules (strip, empty suffix, last-word
duplicate check, one space, empty name) are SS-F-*; the setting and its 20-character limit are
SS-S-*; the render row and the preview use `spoken_text(effective_spoken_name(...), suffix)`
and are SS-R-* and SS-P-*.
