# WPS over Bhoonidhi SAR data

## Topic
Web Processing Service (WPS 1.0.0) built with PyWPS and packaged in Docker.
for the **EOS-04 (RISAT-1A) C-band SAR Level-2B** images from ISRO's [Bhoonidhi](https://bhoonidhi.nrsc.gov.in/) portal. 

## Identified gap
Bhoonidhi has no cloud processing for microwave data.

## Download API constraint
As generation of JWT token requires special account privellages, I downloaded some scenes locally and provided these local scenes to let anyone test standard WPS requests (GetCapabilities, DescribeProcess, Execute).

Level-2B terrain-normalised Gamma0 scenes - **20 scenes** (10 CRS, 10 MRS), the same list as `/scenes`.

| Scene id | Date | Mode | Channels | Pixel size |
|---|---|---|---|---|
| `E04_SAR_MRS_25MAR2022_084011005061_591_STUC00ZTD_273_16_DH_D_R_N22564_E072255` | 2022-03-25 | MRS | HH + HV | 18 m |
| `E04_SAR_CRS_27MAY2022_147123619062_1551_STUC00ZTD_1268_10_DH_A_L_N18883_E075368` | 2022-05-27 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_10JUN2022_161130706028_1763_STUC00ZTD_1478_2_DH_A_R_N09923_E076389` | 2022-06-10 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_06JUL2022_187113003043_2155_STUC00ZTD_1884_2_DH_A_L_N22747_E091391` | 2022-07-06 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_14JUL2022_195131007043_2277_STUC00ZTD_2028_8_DH_A_R_N21224_E072907` | 2022-07-14 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_28JUL2022_209120915085_2488_STUC00ZTD_2251_6_DH_A_L_N22328_E079567` | 2022-07-28 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_03SEP2022_246113639054_3047_STUC00ZTD_2857_5_DH_A_L_N26139_E086891` | 2022-09-03 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_09SEP2022_252120459099_3138_STUC00ZTD_2960_10_DH_A_L_N27798_E081361` | 2022-09-09 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_14SEP2022_257110756342_3213_STUC00ZTD_3060_3_DH_A_L_N23904_E096068` | 2022-09-14 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_20OCT2022_293121938074_3758_STUC00ZTD_3772_3_DH_A_R_N21231_E085557` | 2022-10-20 | CRS | HH + HV | 36 m |
| `E04_SAR_CRS_21OCT2022_294120739036_3773_STUC00ZTD_3790_1_DH_A_L_N16305_E082876` | 2022-10-21 | CRS | HH + HV | 36 m |
| `E04_SAR_MRS_30MAY2023_150235112470_7121_STUC00ZTD_8466_10_DH_D_R_N22565_E091864` | 2023-05-30 | MRS | HH + HV | 18 m |
| `E04_SAR_MRS_27OCT2023_300003548143_9374_STUC00ZTD_11705_14_DH_D_R_N22565_E080660` | 2023-10-27 | MRS | HH + HV | 18 m |
| `E04_SAR_MRS_19DEC2023_353001315426_10175_STUC00ZTD_12829_9_DH_D_R_N22565_E086257` | 2023-12-19 | MRS | HH + HV | 18 m |
| `E04_SAR_MRS_29FEB2024_060010430384_11264_STUC00ZTD_14316_19_DH_D_R_N18728_E072907` | 2024-02-29 | MRS | HH + HV | 18 m |
| `E04_SAR_MRS_08APR2024_099000744899_11853_STUC00ZTD_15036_10_DH_D_R_N21286_E087404` | 2024-04-08 | MRS | HH + HV | 18 m |
| `E04_SAR_MRS_27JUL2024_210000050107_13531_STUC00ZTD_17562_7_DH_D_R_N25120_E089560` | 2024-07-28 | MRS | HH + HV | 18 m |
| `E04_SAR_MRS_23AUG2024_236234459122_13939_STUC00ZTD_18105_11_DH_D_R_N21286_E093020` | 2024-08-23 | MRS | HH + HV | 18 m |
| `E04_SAR_MRS_08MAR2025_067232836601_16917_STUC00ZTD_22680_13_DH_D_R_N17449_E096480` | 2025-03-08 | MRS | HH + HV | 18 m |
| `E04_SAR_MRS_04AUG2025_216122827883_19163_STUC00ZTD_26182_5_DH_A_R_N21233_E082775` | 2025-08-04 | MRS | HH + HV | 18 m |

## Operations available
Standard WPS operations:
- **GetCapabilities**: tells you who made the service and which processes it has.
- **DescribeProcess**: tells you what inputs a process needs and what it gives back.
- **Execute**: runs a process and gives you a link to a ZIP file with the result.

Processes you can Execute:
| Process | In simple words |
|---|---|
| `Subset` | BBox subsetting of the dataset. Gives the raw numbers (DN) and a quality mask. |
| `Linear2dB` | Converts the raw SAR values into real backscatter (Gamma0) in dB. |
| `waterCandidateMask` | Binary Classification (1 = water, 0 = not water). Due to the time restriction a basic classifier (value limit) is implemented as water absorbs microwave a limit of -20 dB has been used. |
| `polarisationRatio` | HV/HH for your box. |

Every process needs `bbox` (lon lat box), `date` (format 2022-05-08) and optionally `scene_id`; Some operations also require `polarization` (HH, HV or DH for both).

## Instructions

The SAR data (about 5 GB) is not in this repository. Put the scene folders into `data/raw/` (see [data/README.md](data/README.md)), then:

```bash
docker compose --env-file config/docker.env up -d --build    # service on http://localhost:5000
```

Stop the service with `docker compose --env-file config/docker.env down`.For a public link run `cloudflared tunnel --url http://localhost:5000`, set the printed URL as `WPS_PUBLIC_URL` in `config/docker.env` and start the service again.
