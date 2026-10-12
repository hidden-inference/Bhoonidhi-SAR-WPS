# WPS over Bhoonidhi SAR data

## Topic

A small **OGC Web Processing Service (WPS 1.0.0)** built with PyWPS and packaged in Docker. It works on **EOS-04 (RISAT-1A) C-band SAR Level-2B** images from ISRO's [Bhoonidhi](https://bhoonidhi.nrsc.gov.in/) portal. Bhoonidhi has no cloud processing for microwave data, so we downloaded some scenes to our own server and let anyone cut, convert and analyse them through standard WPS requests (GetCapabilities, DescribeProcess, Execute).

## Data available

Level-2B terrain-normalised Gamma0 scenes (MRS = Medium Resolution ScanSAR, CRS = Coarse Resolution ScanSAR), area lon 69-97, lat 8-37, years 2021-2026, with HH and HV channels. Currently **15 scenes** (11 CRS, 4 MRS). This is the same list as the `/scenes` page of the running service (the live list there can be longer because downloads continue; `/scenes?all=1` also shows everything Bhoonidhi has online).

| Scene id | Date | Mode | Channels | Pixel size |
|---|---|---|---|---|
| `E04_SAR_MRS_25MAR2022_084011005061_591_STUC00ZTD_273_16_DH_D_R_N22564_E072255` | 2022-03-25 | MRS | HH + HV | 18 m |
| `E04_SAR_CRS_17APR2022_107120919088_946_STUC00ZTD_684_6_DH_A_L_N22739_E081544` | 2022-04-17 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_08MAY2022_128125859021_1264_STUC00ZTD_1008_13_DH_A_R_N21369_E076607` | 2022-05-08 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_19MAY2022_139123043049_1430_STUC00ZTD_1166_12_DH_A_L_N18974_E077229` | 2022-05-19 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_20MAY2022_140121931071_1445_STUC00ZTD_1174_12_DH_A_L_N18849_E079403` | 2022-05-20 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_25MAY2022_145125756072_1521_STUC00ZTD_1246_10_DH_A_R_N17532_E077336` | 2022-05-25 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_27MAY2022_147123356060_1551_STUC00ZTD_1268_3_DH_A_L_N09913_E077354` | 2022-05-27 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_27MAY2022_147123619062_1551_STUC00ZTD_1268_10_DH_A_L_N18883_E075368` | 2022-05-27 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_02JUN2022_153130252059_1642_STUC00ZTD_1347_7_DH_A_R_N15022_E076704` | 2022-06-02 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_10JUN2022_161130706028_1763_STUC00ZTD_1478_2_DH_A_R_N09923_E076389` | 2022-06-10 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_05JUL2022_186131422079_2141_STUC00ZTD_1867_2_DH_A_R_N16218_E073161` | 2022-07-05 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_06JUL2022_187113003043_2155_STUC00ZTD_1884_2_DH_A_L_N22747_E091391` | 2022-07-06 | CRS | HH + HV | 36 m |
| `E04_SAR_MRS_03OCT2022_276001135018_3493_STUC00ZTD_3404_2_DH_D_R_N31497_E088026` | 2022-10-03 | MRS | HH + HV | 18 m |
| `E04_SAR_MRS_19DEC2022_353000652037_4657_STUC00ZTD_4961_5_DH_D_R_N27672_E088663` | 2022-12-19 | MRS | HH + HV | 18 m |
| `E04_SAR_MRS_03FEB2023_034010329027_5353_STUC00ZTD_5817_14_DH_D_R_N25120_E074155` | 2023-02-03 | MRS | HH + HV | 18 m |

The data itself is not in this repo (it is big). See "How to run" to download it.

## Operations available

Standard WPS operations:

- **GetCapabilities**: tells you who made the service and which processes it has.
- **DescribeProcess**: tells you what inputs a process needs and what it gives back.
- **Execute**: runs a process and gives you a link to a ZIP file with the result.

Processes you can Execute:

| Process | In simple words |
|---|---|
| `Subset` | Cuts out the part of the image inside your box. Gives the raw numbers (DN) and a quality mask. |
| `Linear2dB` | Cuts your box and turns the raw numbers into real backscatter (Gamma0) in dB. |
| `waterCandidateMask` | Marks the very dark pixels in your box as possible water (1 = maybe water, 0 = not water). Default limit is -20 dB, you can change it. |
| `polarisationRatio` | Shows how strong HH is compared to HV (HH minus HV in dB) for your box. |

Every process needs `bbox` (lon lat box), `date` (like 2022-05-08) and optionally `scene_id`; the ones that need it also take `polarization` (HH, HV or DH for both). Ready-made request files are in `requests/`.

## How to run

```bash
# 1. get data (needs a Bhoonidhi account; the password is only kept in memory)
python -m venv .venv && .venv/bin/pip install -r requirements.txt requests
export BHOONIDHI_USER=your_id BHOONIDHI_PASSWORD=your_password
.venv/bin/python fetch_bhoonidhi.py --target 50          # downloads 50 scenes into data/raw

# 2. start the service
docker compose --env-file config/docker.env up -d --build   # http://localhost:5000

# 3. try the three operations
curl 'http://localhost:5000/wps?service=WPS&request=GetCapabilities&acceptversions=1.0.0'
curl 'http://localhost:5000/wps?service=WPS&version=1.0.0&request=DescribeProcess&identifier=Linear2dB'
curl -H 'Content-Type: text/xml' --data-binary @requests/Linear2dB.xml http://localhost:5000/wps
```

The Execute answer contains a `Reference` link to `result.zip`. Other useful pages: `/scenes`, `/example.xml?process=Subset&scene_id=<id>` (a ready request for any scene), `/simple/capabilities` (a flat, easy to read XML view) and `/health`. To share it online use `cloudflared tunnel --url http://localhost:5000` and put the link in `config/docker.env` as `WPS_PUBLIC_URL`.

Note: `requests/` examples point to scene `E04_SAR_CRS_08MAY2022_...`; use `/example.xml` if you downloaded different scenes.

## File structure

```
.
├── app.py                   # Flask + PyWPS app (/wps, /scenes, /example.xml, /simple/...)
├── pywps.cfg                # WPS settings and provider/contact details
├── Dockerfile               # image: Python + GDAL + PyWPS + gunicorn
├── compose.yaml             # runs the container, mounts data/outputs/work/logs
├── config/docker.env        # WPS_PUBLIC_URL for docker compose
├── requirements.txt         # numpy, scipy, rasterio
├── requirements-wps.txt     # pywps, flask, gunicorn, requests
├── fetch_bhoonidhi.py       # downloads L2B scenes from Bhoonidhi (resumable, only needed files)
├── run_local.py             # run a process without the server
├── processes/
│   └── eos04_process.py     # the 4 WPS processes (inputs, outputs, descriptions)
├── processing/              # the SAR code behind the processes
│   ├── metadata.py          # reads BAND_META.txt of an L2B scene
│   ├── catalog.py           # scene catalogue and scene selection
│   ├── subset.py            # bounding box to raster window
│   ├── calibration.py       # DN to Gamma0 (linear and dB)
│   ├── speckle.py           # 3x3 Lee speckle filter
│   ├── export.py            # GeoTIFF, metadata.json and ZIP writer
│   └── pipeline.py          # ties it together for each process
├── templates/               # our GetCapabilities template (provider block)
├── requests/                # example Execute requests (XML)
├── scripts/
│   ├── example_request.py   # builds the /example.xml request
│   └── ingest_local.py      # adds a manually downloaded ZIP / rebuilds the catalogue
└── data/ outputs/ work/ logs/   # created at run time, not in git
```

## Limits

The water mask is a plain threshold (default -20 dB is a demo value, not validated for any area), so it is not a flood map. Calibration follows the EOS-04 data product format document, section 6.3.
