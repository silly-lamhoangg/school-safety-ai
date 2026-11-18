from getpass import getpass

from database.database import init_database, create_user


def main():
    init_database()

    print("===== TAO TAI KHOAN GIAM THI =====")

    username = input("Ten dang nhap: ").strip()
    full_name = input("Ho va ten: ").strip()

    password = getpass("Mat khau: ")
    confirm_password = getpass("Nhap lai mat khau: ")

    if password != confirm_password:
        print("Mat khau nhap lai khong khop!")
        return

    try:
        created = create_user(
            username,
            password,
            full_name
        )

        if created:
            print("TAO TAI KHOAN THANH CONG!")
        else:
            print("Ten dang nhap da ton tai!")

    except ValueError as e:
        print("LOI:", e)


if __name__ == "__main__":
    main()