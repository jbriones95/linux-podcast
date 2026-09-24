import sys

from .application import PostcastApplication


def main():
    app = PostcastApplication()
    app.run(sys.argv)


if __name__ == "__main__":
    main()