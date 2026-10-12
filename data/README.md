# data

This is where the locally downloaded SAR data is placed. It is **not pushed to the repository** because the data is about 5 GB.

Put one folder per EOS-04 Level-2B scene inside `data/raw/`, exactly as extracted from Bhoonidhi (the folder name is the scene id):

```
data/raw/<scene_id>/
├── BAND_META.txt
├── <scene_id>_mask.tif
├── scene_HH/imagery_HH.tif
└── scene_HV/imagery_HV.tif
```

The service reads `data/raw/` when it starts (`docker compose ... restart` after adding scenes). The scenes it found are listed at `http://localhost:5000/scenes`.
