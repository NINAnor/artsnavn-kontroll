#!/usr/bin/env python3

import concurrent.futures
import csv
import io
import json
import os
from itertools import batched
from pathlib import Path

import requests
from pywebio import start_server
from pywebio.output import (
    put_buttons,
    put_file,
    put_html,
    put_image,
    put_info,
    put_progressbar,
    put_table,
    set_progressbar,
    use_scope,
)
from pywebio.pin import pin, put_textarea
from pywebio.session import run_js, set_env

ENDPOINT = os.getenv(
    "RECONCILE_ENDPOINT", "http://datasette:8001/common/species/-/reconcile"
)

COLUMNS = [
    "ValidScientificName",
    "ValidScientificNameId",
    "Kingdom",
    "Phylum",
    "Class",
    "Order",
    "Family",
    "Genus",
    "Species",
    "SubSpecies",
    "ValidScientificNameAuthorship",
    "PrefferedPopularname",
]

TITLE = "Kontroll av artsnavn mot Artsnavnebasen"
INTRO = """
<h1>Kontroll av artsnavn mot Artsnavnebasen</h1>

<p>Skjemaet bruker Artsdatabanken sine webservices til å sjekke hvert enkelt artsnavn online mot databasen. Lim inn listen med latinske artsnavn under. Når resultatet vises kan du kopiere tabellen og lime inn i excel ved å klikke på knappen.</p>

<p><b>Tips!</b> Lim inn som rein tekst i excel ved å velge "Match Destination Formatting".</p>
"""
IMAGE = open(Path(__file__).parent / "static/matchdestination.png", "rb").read()

PAGE_SIZE = 100
PREVIEW_SIZE = 1000

headers = {"Content-Type": "application/x-www-form-urlencoded"}

js_copy_table = """(
function() {
    let table = document.querySelector('#pywebio-scope-result table');
    let range = document.createRange();
    range.selectNode(table);
    window.getSelection().addRange(range);
    document.execCommand('copy');
})()
"""


def buttons_callback(value):
    if value == "check":
        generate_table(pin.species_textarea)
    elif value == "copy":
        run_js(js_copy_table)


def webapp():
    set_env(title=TITLE, output_max_width="100%")
    put_html(INTRO)
    put_image(IMAGE)
    put_textarea("species_textarea")
    put_buttons(
        [
            {"label": "Sjekk artsnavn", "value": "check"},
            {"label": "Kopier resultat", "value": "copy", "color": "success"},
        ],
        onclick=buttons_callback,
    )


def get_species(text):
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        yield line


def get_species_data(species):
    species_data = []
    data = {
        "queries": json.dumps(
            {str(index): {"query": specie} for index, specie in enumerate(species)}
        )
    }
    response = requests.post(ENDPOINT, data=data, headers=headers).json()
    specie_ids = []
    for index, specie in enumerate(species):
        specie_ids.append(response[str(index)]["result"][0]["id"])
    data = {
        "extend": json.dumps(
            {
                "ids": specie_ids,
                "properties": [{"id": column} for column in COLUMNS],
            }
        )
    }
    response = requests.post(ENDPOINT, data=data, headers=headers).json()
    for specie_id in specie_ids:
        attributes = response["rows"][specie_id]
        table_row = {}
        for key, value in attributes.items():
            value = value[0]["str"]  # take the first result
            if value:
                table_row[key] = value
        species_data.append(table_row)
    return species_data


def generate_table(text):
    with use_scope("result", clear=True):
        put_progressbar("bar", auto_close=True)
        species = list(get_species(text))
        table = []
        with concurrent.futures.ProcessPoolExecutor() as pool:
            for species_data in pool.map(
                get_species_data, batched(get_species(text), PAGE_SIZE)
            ):
                table.extend(species_data)
                progress = len(table) / len(species)
                set_progressbar("bar", progress)
        if len(table) <= PREVIEW_SIZE:
            put_table(table, header=COLUMNS)
        else:
            buffer = io.StringIO()
            csv_writer = csv.writer(buffer)
            csv_writer.writerow(COLUMNS)
            csv_writer.writerows(table)
            put_info(
                "Mer enn %d arter: tabellen er for stor til å vises." % PREVIEW_SIZE,
                put_file("arter.csv", buffer.getvalue().encode("utf8"), "Last ned CSV"),
            )


def main():
    start_server(webapp, port=8080)


if __name__ == "__main__":
    main()
