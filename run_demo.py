#!/usr/bin/env python3

import argparse
import logging
import shutil
from pathlib import Path

home_dir = Path.home() / "princeton-iot-inspector" / ".configs"

if __name__ == "__main__":
    logging.basicConfig(
        format="[%(asctime)s] (%(levelname)s) %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO,
    )

    parser = argparse.ArgumentParser(
        prog="run_demo.py",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "updater_pid",
        help="The PID of the client that should run the update",
        type=int,
    )
    parser.add_argument(
        "data_file",
        help="Parquet file with data for client",
    )
    parser.add_argument(
        "-p",
        "--peers",
        nargs="+",
        type=int,
        help="The PID(s) of clients that should act as peers",
    )

    args = parser.parse_args()
    logger = logging.getLogger()

    # Create a file to designate the client with PID updater_pid
    # to initiate a computation
    initiator_dir = home_dir / str(args.updater_pid)
    (initiator_dir / "start_computation").touch()
    logger.info("Designated PID %d as initiator", args.updater_pid)

    peers = args.peers if args.peers is not None else []
    for peer in peers:
        (home_dir / str(peer) / "start_peer").touch()
        logger.info("Designated PID %d as a peer", peer)

    data_file = Path(args.data_file)
    output_path = initiator_dir / "features.pq"
    shutil.copy(data_file, initiator_dir / "features.pq")
    logger.info("Wrote %s to %s", data_file, output_path)
