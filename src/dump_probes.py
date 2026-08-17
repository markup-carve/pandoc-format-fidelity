"""Write the probe set as JSON, for lanes that are not Python (run_carve.mjs)."""
import json

from probes import PROBES, API
from run_meta import BLOCKS, META

json.dump({"api": API,
           "probes": {n: {"rich": p["rich"], "degraded": p["degraded"]}
                      for n, p in PROBES.items()},
           "meta": META,
           "metaBlocks": BLOCKS},
          open("results/probes.json", "w"))
print("results/probes.json:", len(PROBES), "probes")
