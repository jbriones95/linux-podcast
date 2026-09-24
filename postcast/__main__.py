import sys

from .application import PostcastApplication


def main(argv=None):
    if argv is None:
        argv = sys.argv
    app = PostcastApplication()
    app.run(argv)


if __name__ == "__main__":
    main()