"""Made-up labelled name pairs (typed name, heard word) for the sound-alike matcher (AC1).

Only common given names and invented spellings; no real voter data.
"""

from __future__ import annotations

# (typed, heard): same name, different script or spelling. Must match at 90 % or better.
MATCHING_PAIRS: list[tuple[str, str]] = [
    ("Krishan", "कृष्ण"),
    ("Krishan", "किशन"),
    ("Krishan", "krishan"),
    ("Krishan", "Krishn"),
    ("Krishan", "Kishan"),
    ("Ramesh", "रमेश"),
    ("Suresh", "सुरेश"),
    ("Mahesh", "महेश"),
    ("Rajesh", "राजेश"),
    ("Deepak", "दीपक"),
    ("Anil", "अनिल"),
    ("Sunil", "सुनील"),
    ("Vijay", "विजय"),
    ("Vikram", "विक्रम"),
    ("Pooja", "पूजा"),
    ("Priya", "प्रिया"),
    ("Geeta", "गीता"),
    ("Ganesh", "गणेश"),
    ("Mohan", "मोहन"),
    ("Kavita", "कविता"),
    ("Amit", "अमित"),
    ("Vishal", "विशाल"),
    ("Sanjay", "संजय"),
    ("Pankaj", "पंकज"),
    ("Pawan", "पवन"),
    ("Wasim", "वसीम"),
    ("Phool", "फूल"),
    ("Ashok", "अशोक"),
    ("Rahul", "राहुल"),
    ("Vijay", "Wijay"),
    ("Shyam", "Syam"),
    ("Phool", "Fool"),
    ("Sunil", "Suneel"),
    ("Anil", "Aneel"),
    ("Geeta", "Gita"),
    ("Ramesh", "Rameshh"),
]

# Different names: must NOT reach the default closeness of 0.8.
UNRELATED_PAIRS: list[tuple[str, str]] = [
    ("Krishan", "Ramesh"),
    ("Krishan", "रमेश"),
    ("Anil", "Vikram"),
    ("Deepak", "Ganesh"),
    ("Pooja", "Rahul"),
    ("Sita", "Mohan"),
    ("Neha", "विक्रम"),
    ("Amit", "सुरेश"),
    ("Priya", "हरीश"),
    ("Kavita", "Ashok"),
    ("Lakshmi", "Farhan"),
    ("Sanjay", "Deepak"),
    ("Wasim", "Ganesh"),
    ("Pankaj", "Neha"),
]
