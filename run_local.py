"""Run one process locally without the WPS server, e.g.
  python run_local.py linear2db --bbox 76.70 21.20 76.80 21.30 --date 2022-05-08 --output outputs/my-run"""
import argparse
from processing.pipeline import run_pipeline, BASE, PRODUCTS


def main():
    p = argparse.ArgumentParser(description='EOS-04 L2B processing without WPS')
    p.add_argument('product', choices=PRODUCTS)
    p.add_argument('--bbox', nargs=4, type=float, required=True)
    p.add_argument('--date', required=True)
    p.add_argument('--polarization', choices=['HH', 'HV', 'DH'], default='DH')
    p.add_argument('--scene-id')
    p.add_argument('--threshold-db', type=float, help='water: dB threshold (default -20)')
    p.add_argument('--enl', type=float, help='water: optional Lee filter ENL')
    p.add_argument('--catalog', default=str(BASE/'data/catalog/scenes.json'))
    p.add_argument('--output', dest='output_dir', required=True)
    args = vars(p.parse_args())
    try:
        print(run_pipeline(**args))
    except (ValueError, OSError) as exc:
        p.exit(2, f'Error: {exc}\n')

if __name__ == '__main__':
    main()
