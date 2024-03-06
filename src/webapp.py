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
    put_button,
    put_html,
    put_image,
    put_progressbar,
    put_success,
    put_table,
    put_warning,
    set_progressbar,
    use_scope,
)
from pywebio.pin import pin, put_textarea
from pywebio.session import download, run_js, set_env

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

TITLE = "Kontroll av artsnavn"
INTRO = """
<h1>Kontroll av artsnavn</h1>

<p>Skjemaet bruker en copi av Artsdatabanken artsnavn til å sjekke hvert enkelt artsnavn online mot databasen. Lim inn listen med latinske artsnavn under. Når resultatet vises kan du kopiere eller last ned tabellen.</p>
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


def webapp():
    set_env(title=TITLE, output_max_width="100%")
    put_html(INTRO)
    put_textarea("species_textarea")
    put_button("Sjekk artsnavn", onclick=lambda: generate_table(pin.species_textarea))


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
            {
                str(index): {"query": specie, "limit": 1}
                for index, specie in enumerate(species)
            }
        )
    }
    response = requests.post(ENDPOINT, data=data, headers=headers).json()
    specie_ids = []
    for index, specie in enumerate(species):
        result = response[str(index)]["result"][0]
        specie_ids.append((result["id"], result["score"]))
    data = {
        "extend": json.dumps(
            {
                "ids": [specie_id for specie_id, _ in specie_ids],
                "properties": [{"id": column} for column in COLUMNS],
            }
        )
    }
    response = requests.post(ENDPOINT, data=data, headers=headers).json()
    for specie_id, specie_score in specie_ids:
        attributes = response["rows"][specie_id]
        table_row = {"Score": specie_score}
        for key, value in attributes.items():
            value = value[0]["str"]  # take the first result
            if value:
                table_row[key] = value
        species_data.append(table_row)
    return species_data


def table_to_csv(table):
    buffer = io.StringIO()
    csv_writer = csv.writer(buffer)
    csv_writer.writerow(COLUMNS)
    csv_writer.writerows(table)
    return buffer.getvalue().encode("utf8")


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
        message = [
            "%d ligne(r) behandlet." % len(table),
            put_button(
                "Last ned CSV", lambda: download("arter.csv", table_to_csv(table))
            ),
        ]
        table_preview = len(table) <= PREVIEW_SIZE
        if table_preview:
            message[1:1] = [
                put_html(
                    """<b>Tips!</b> Lim inn som rein tekst i Excel ved å velge "Match Destination Formatting"."""
                ),
                put_image(IMAGE),
                put_button(
                    "Kopier resultat",
                    onclick=lambda: run_js(js_copy_table),
                ),
            ]
        else:
            message[1:1] = [
                "Mer enn %d ligner: tabellen er for stor til å vises." % PREVIEW_SIZE,
            ]
        put_success(*message)
        worse_score = min(row["Score"] for row in table)
        if worse_score < 90:
            put_warning(
                (
                    "Linjer med lav Score har blitt oppdaget. "
                    "Kontroller verdien i Score-kolonnen. "
                    "Verdiene går fra 0 til 100, der 100 er en perfekt match. "
                    "Det anbefales å sjekke linjer med poengsum under 90."
                )
            )
        if table_preview:
            put_table(
                table,
                header=[
                    "Score",
                ]
                + COLUMNS,
            )


def main():
    start_server(webapp, port=8080)


if __name__ == "__main__":
    main()
