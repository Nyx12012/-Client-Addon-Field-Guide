# Field Guide

A TavernLauncher addon: a reference book for A Township Tale that you fill with packs.

It comes empty. A pack is one JSON file someone made: a cooking guide, a table of every metal, notes for one server. Import the packs you want, turn them on and off, and read them offline. Packs are plain data. Opening one can never run anything on your computer.

## Install

1. Copy the `fieldguide` folder into the `addons` folder next to `TavernLauncher - Client.exe`.
2. Open TavernLauncher, click **🧩 Addons**, tick **Field Guide**, click **Save**, then restart the launcher.

A **📖 Field Guide** button appears next to 🧩 TavernKeeper.

## Using it

- **Import** takes one or more pack files, or a bundle file holding many packs.
- **Packs** lists what is installed. Turn a pack off to hide it, export it, or remove it. Removed packs go to a `removed` folder, so nothing is lost by accident.
- **New page** writes a page into My Notes. To share your pages, click **New pack** in Packs, add pages to it, and export it.
- Search covers titles, chapters, tags, text and tables. Type `#` and a keyword, like `#smelting`, to list every page with that tag. Click a tag on a page, or a keyword on the home page, to do the same.
- Click a table heading to sort by it. Double click a row to open the page it links to.

Your packs and settings live in `%APPDATA%\TheModdingTavern\fieldguide\`. Nothing is uploaded anywhere.

## Writing a pack

```json
{
  "format": "tavern-fieldguide-pack",
  "format_version": 2,
  "id": "yourname.yourpack",
  "title": "Your pack",
  "description": "One line about it.",
  "category": "Players",
  "version": "1.0.0",
  "author": "You",
  "license": "CC0-1.0",
  "verified_against": "main-1.7.2.1.42203",
  "verified_on": "2026-10-09",
  "servers": ["*"],
  "home": "A page",
  "pages": [
    {
      "id": "a-page",
      "title": "A page",
      "chapter": "Basics",
      "tags": ["example"],
      "sections": [
        { "heading": "Some text", "body": "Text with a link to [[Another page]]." },
        {
          "heading": "Some numbers",
          "table": {
            "columns": ["Metal", "Melting point"],
            "rows": [["[[Iron]]", 1200], ["Copper", 1085]],
            "note": "Where the numbers came from."
          }
        }
      ]
    }
  ]
}
```

Only `pages` is required. Links go by page title and can point into any pack that is turned on. `servers` takes `["*"]` for every server, or host names to show the pack only while the launcher is pointed at one of them.

`verified_against` names the game build the pack was checked against. Leave it empty if you have not checked, and the guide says so.

If the text came from somewhere else, fill in `attribution` and `license`. Community wikis are usually CC BY-SA, which means you must credit the source.

A bundle is many packs in one file:

```json
{ "format": "tavern-fieldguide-bundle", "format_version": 2, "title": "My packs", "packs": [ ] }
```

Field Guide 1.x packs (format 1) still load.
