import json
import sys

from pathlib import Path

def get_property(properties, name, default = None):
    for property in properties:
        if property["name"] == name:
            return property["value"]
    return default

def convert_tiled_map(input_path):
    with open(input_path, "r") as f:
        tiled = json.load(f)

    width = tiled["width"]
    height = tiled["height"]

    runtime_map = {
        "MachineName": get_property(tiled["properties"], "MachineName"),
        "Name": get_property(tiled["properties"], "Name"),
        "TileSheetName": get_property(tiled["properties"], "TileSheetName"),
        "AnimatedTileSheetName": get_property(tiled["properties"], "AnimatedTileSheetName"),
        "BackgroundArtName": get_property(tiled["properties"], "BackgroundArtName"),
        "Width": width,
        "Height": height,
        "Tiles": []
    }

    tile_layers = [
        layer for layer in tiled["layers"]
        if layer["type"] == "tilelayer"
    ]

    starting_animated_gid = get_property(tiled["properties"], "StartingAnimatedGID")
    starting_animated_index = get_property(tiled["properties"], "StartingAnimatedTileIndex")

    for y in range(height):
        for x in range(width):

            objects = []

            index = y * width + x

            for layer in tile_layers:
                gid = layer["data"][index]

                if gid >= starting_animated_gid:
                    gid = starting_animated_index + (gid - starting_animated_gid)

                if gid != 0:
                    objects.append(gid)

            runtime_map["Tiles"].append({
                "X": x,
                "Y": y,
                "Objects": objects
            })

    output_path = Path(input_path).with_suffix(".converted.json")

    with open(output_path, "w") as f:
        json.dump(runtime_map, f, indent = 4)

    print(f"Converted map written to: {output_path}")


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage: python convert_map.py <tiled_map.json>")
        sys.exit(1)

    convert_tiled_map(sys.argv[1])