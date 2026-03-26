import sys

from app.bootstrap.app_factory import create_application


if __name__ == "__main__":
    app, main_window = create_application(sys.argv)
    main_window.show()
    sys.exit(app.exec_())

