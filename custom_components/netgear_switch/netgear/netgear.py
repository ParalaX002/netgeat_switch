import requests
import hashlib
import pickle
import os
import datetime
from lxml import html


class netgear:
    """
    Class to access information and set poe ports on switch with v3 firmware of netgear (for instance GS316EPP"""

    m_name = None
    m_session = requests.Session()
    m_last_update = datetime.datetime.fromtimestamp(0)
    m_loggedin = False

    def __init__(self, host: str = "", password: str = "") -> None:
        """Constructor

        :param host: The ip address of the switch, defaults to ""
        :type host: str, optional
        :param password: The password to login in the switch, defaults to ""
        :type password: str, optional
        """
        self.m_gambit = ""
        self.m_session_file = "session"

        self.m_host = host
        self.m_password = password

        self.m_switch_type = ""
        self.m_ports_status = {}

    def merge(self, str1: str, str2: str) -> str:
        """Merge two strings by concatenating them together

        :param str1: The first string to merge
        :type str1: str
        :param str2: The second string to merge
        :type str2: str
        :return: The resulting string
        :rtype: str
        """
        arr1 = list(str1)
        arr2 = list(str2)
        result = ""
        index1 = 0
        index2 = 0
        while index1 < len(arr1) or index2 < len(arr2):
            if index1 < len(arr1):
                result += arr1[index1]
                index1 += 1
            if index2 < len(arr2):
                result += arr2[index2]
                index2 += 1
        return result

    def modification_date(self, filename: str) -> datetime.datetime:
        """Return the modification date of a file

        :param filename: The filename to get the timestamp from
        :type filename: str
        :return: The modification date
        :rtype: datetime.datetime"""

        t = os.path.getmtime(filename)
        return datetime.datetime.fromtimestamp(t)

    def ask_switch_info(self) -> str:
        """Recover the switch type

        :return: The switch type
        :rtype: str
        """
        if not self.m_gambit:
            return ""

        if self.m_name:
            return self.m_name

        # Now, recover the homepage and thus the switch name
        header = {
            "Accept": "text/plain, */*; q=0.01",
            "Referer": "http://" + self.m_host + "/homepage.html",
        }
        cookie = {"gambitCookie": self.m_gambit}
        home_request = self.m_session.get(
            f"http://{self.m_host}/iss/specific/dashboard.html?Gambit={self.m_gambit}",
            timeout=5,
            cookies=cookie,
            headers=header,
        )

        tree = html.fromstring(home_request.content)
        name = tree.xpath('//p[@id="model_name"]/text()')
        if len(name) >= 1:
            self.m_name = name[0]
            return self.m_name

        return None

    def ask_port_info(self) -> bool:
        """Recover the information of the ports.

        Information are never retreived if they are less than 60s old

        :return: True if the port information has been successfully fetched
        :rtype: bool
        """

        # How old is the information?
        print("Asking for port info")
        if (datetime.datetime.now() - self.m_last_update).seconds < 60:
            print("Information is fresh, returning")
            return True

        # Are we still logged in?
        if not self.ask_switch_info():
            print("Not logged in")
            if self.login() != 200:
                print("Still no logged in")
                return False

        print("Logged in")

        # We need to set update before really asking, otherwise, all entities will send the request directly (Joys of multithreading)
        # This is by no mean perfect since the result of the askers will be all delayed except the one that executed the request...
        self.m_last_update = datetime.datetime.now()

        # Recover the POE status:
        cookie = {
            "gambitCookie": self.m_gambit,
        }

        header = {
            "Accept": "text/plain, */*; q=0.01",
            "Referer": "http://" + self.m_host + "/homepage.html",
        }

        poe_status_request = self.m_session.get(
            f"http://{self.m_host}/iss/specific/poePortStatus.html?Gambit={self.m_gambit}&GetData=TRUE",
            cookies=cookie,
            headers=header,
        )
        tree = html.fromstring(poe_status_request.content)
        out_volt = tree.xpath('//p[@class="bold-title OutputVoltage-text"]/text()')
        out_cur = tree.xpath('//p[@class="bold-title OutputCurrent-text"]/text()')
        out_pow = tree.xpath('//p[@class="bold-title OutputPower-text"]/text()')
        temp = tree.xpath('//p[@class="bold-title Temperature-text"]/text()')
        status = tree.xpath('//span[@class="bold-title Status-text"]/text()')

        ports = []
        for i in range(0, 15):
            if len(out_volt) > i:
                ports.append(
                    {
                        "Voltage": out_volt[i],
                        "Current": out_cur[i],
                        "Power": out_pow[i],
                        "Temperature": temp[i],
                        "Status": status[i],
                    }
                )

        if len(ports) == 0:
            # Something went wrong
            return False

        self.m_ports_status = ports
        return True

    def login(self) -> int:
        """Check if we are already logged in the device. If so, check that the login is still valid. If we are not logged in, then log in.

        :return: Error code, as in html error codes (200 = success, 404 = bad host, 403 = bad credential)
        :rtype: int
        """

        # Check if there is a session file
        if os.path.exists(self.m_session_file):
            time = self.modification_date(self.m_session_file)

            # Only load if file less than 30 minutes old
            last_modification = (datetime.datetime.now() - time).seconds
            if last_modification < 30 * 60:
                # Load the session
                with open(self.m_session_file, "rb") as f:
                    self.m_session = pickle.load(f)

                # Also load the gambit file
                with open("gambit", "r", encoding="utf8") as f:
                    self.m_gambit = f.readline()

                # Also get the name if not already there
                if not self.m_name:
                    self.ask_switch_info()

                return 200

        # No file or too old, start a new session
        try:
            login_page_request = self.m_session.get(
                f"http://{self.m_host}/wmi/login", timeout=5
            )
        except requests.exceptions.ConnectTimeout:
            return 400

        tree = html.fromstring(login_page_request.content)
        rand = tree.xpath('//input[@id="rand"]/@value[1]')
        payload = None

        rand = rand[0]
        merged = self.merge(self.m_password, rand)
        password = hashlib.md5(str.encode(merged))

        payload = {
            "LoginPassword": password.hexdigest(),
        }

        login_request = self.m_session.post(
            f"http://{self.m_host}/redirect.html", data=payload, timeout=5
        )

        # Try to get a rand number, which means we would be again on the login page, in which case login failed
        tree = html.fromstring(login_request.content)
        rand = tree.xpath('//input[@id="rand"]/@value[1]')
        if rand:
            return 403

        tree = html.fromstring(login_request.content)
        self.m_gambit = tree.xpath('//input[@name="Gambit"]/@value[1]')[0]

        # Save the gambit and dump the session
        f = open("gambit", "w", encoding="utf-8")
        f.write(str(self.m_gambit))
        f.close()

        with open("session", "wb") as f:
            pickle.dump(self.m_session, f)

        # Also get the name if not already there (first connection)
        if not self.m_name:
            self.ask_switch_info()

        return 200

    def get_port_status(self) -> list:
        """
        Recover the port information, as an array

        :return: An array of ports, each containing a dictionnary with the following keys: Voltage, Current, Power, Temperature, Status. Each value is a string as given by the switch
        :rtype: int
        """
        if not self.m_ports_status:
            self.ask_port_info()
        return self.m_ports_status

    def get_switch_name(self) -> str:
        """
        Return the switch name, or None if never connected and not connectable

        :return: The switch name or None
        :rtype: str
        """
        return self.m_name

    def set_port(self, port_nb: int, enabled: bool) -> bool:
        """Set a port to enabled or disabled

        :param port_nb: The port number (starting at 1, as with the switch interface)
        :type port_nb: int
        :param enabled: True to enable, False to disable
        :type enabled: bool
        :return: True if success, False otherwise
        :rtype: int
        """

        # Are we still logged in?
        if not self.ask_switch_info():
            if self.login() != 200:
                return False

        if port_nb < 1 or port_nb > 16:
            return False
        if enabled:
            enable_string = "1"
        else:
            enable_string = "0"

        payload = {
            "TYPE": "submitPoe",
            "PORT_NO": str(port_nb),
            "POWER_LIMIT_VALUE": "300",
            "PRIORITY": "NOTSET",
            "POWER_MODE": "NOTSET",
            "POWER_LIMIT_TYPE": "NOTSET",
            "DETECTION": "NOTSET",
            "ADMIN_STATE": enable_string,
            "Gambit": self.m_gambit,
            "TYPE MIME": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        header = {
            "Accept": "text/plain, */*; q=0.01",
            "Referer": "http://" + self.m_host + "/homepage.html",
        }

        cookie = {"gambitCookie": self.m_gambit}

        poe_request = self.m_session.post(
            f"http://{self.m_host}/iss/specific/poePortConf.html",
            data=payload,
            cookies=cookie,
            headers=header,
        )
        poe_request.raise_for_status()

        # Next time we must refresh, so reset date to epoch
        self.m_last_update = datetime.datetime.fromtimestamp(0)
        return True
