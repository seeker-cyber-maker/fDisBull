"""Repository CLI shim for the original-backed DinoPark Z service."""
from fdisbull.dinopark_z import main

if __name__ == "__main__":
    raise SystemExit(main())
