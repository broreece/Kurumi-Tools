import json
import sys

from pathlib import Path


def get_property(properties, name, default=None):
    for property in properties:
        if property["name"] == name:
            return property["value"]
    return default


def convert_tiled_map(input_path):
    with open(input_path, "r") as f:
        tiled = json.load(f)

    width = tiled["width"]
    height = tiled["height"]
    tile_width = tiled["tilewidth"]
    tile_height = tiled["tileheight"]

    runtime_map = {
        "MachineName": get_property(tiled["properties"], "MachineName"),
        "Name": get_property(tiled["properties"], "Name"),
        "TileSheetName": get_property(tiled["properties"], "TileSheetName"),
        "BackgroundArtName": get_property(tiled["properties"], "BackgroundArtName"),
        "Width": width,
        "Height": height,
        "Tiles": [],
        "Actors": []
    }

    tile_layers = [
        layer for layer in tiled["layers"]
        if layer["type"] == "tilelayer"
    ]

    for y in range(height):
        for x in range(width):

            objects = []

            index = y * width + x

            for layer in tile_layers:
                gid = layer["data"][index]

                if gid != 0:
                    objects.append(gid)

            runtime_map["Tiles"].append({
                "X": x,
                "Y": y,
                "Objects": objects
            })

    object_layers = [
        layer for layer in tiled["layers"]
        if layer["type"] == "objectgroup"
    ]

    for layer in object_layers:
        for obj in layer["objects"]:

            if obj.get("type") != "Actor":
                continue

            props = obj.get("properties", [])

            actor = {
                "ActorKey": get_property(props, "ActorKey"),
                "ActorID": get_property(props, "ActorID", 0),
                "XLocation": int(obj["x"] / tile_width),
                "YLocation": int(obj["y"] / tile_height) - 1,
                "Facing": get_property(props, "Facing", 2),
                "Visible": get_property(props, "Visible", True)
            }

            runtime_map["Actors"].append(actor)

    output_path = Path(input_path).with_suffix(".converted.json")

    with open(output_path, "w") as f:
        json.dump(runtime_map, f, indent=4)

    print(f"Converted map written to: {output_path}")


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage: python convert_map.py <tiled_map.json>")
        sys.exit(1)

    convert_tiled_map(sys.argv[1])