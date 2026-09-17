import QtQuick 6.11
import QtQuick.Controls 6.11
import QtQuick.Layouts 6.11
import QtQuick.Window 6.11
import QtQuick.Effects 6.11

ApplicationWindow {
    id: window
    objectName: "peaksWindow"
    visible: true
    width: 1360
    height: 860
    minimumWidth: 1024
    minimumHeight: 640
    title: "Peaks"
    color: window.ink

    // The Python bridge is intentionally the only stateful dependency of this view.
    // A null bridge keeps the QML useful in designer and offscreen smoke tests.
    readonly property var bridge: (typeof controller === "undefined" ? null : controller)
    readonly property color ink: "#090A0D"
    readonly property color panel: "#101216"
    readonly property color panelRaised: "#16181D"
    readonly property color panelHover: "#1C1F26"
    readonly property color line: "#282C34"
    readonly property color textPrimary: "#F1F2F0"
    readonly property color textSecondary: "#9A9EA7"
    readonly property color textQuiet: "#666A74"
    readonly property color accent: "#A8CEFF"
    readonly property color accentStrong: "#6FA7F4"
    readonly property color good: "#77D6A5"
    readonly property color warn: "#E9BE77"
    readonly property color danger: "#F18586"
    readonly property int radius: 12

    readonly property string page: bridge && bridge.page ? String(bridge.page) : "overview"
    readonly property bool locked: bridge && bridge.locked ? true : false
    readonly property bool hasPasscode: bridge && bridge.hasPasscode ? true : false
    readonly property string pinMode: bridge && bridge.pinMode ? String(bridge.pinMode) : "unlock"
    readonly property string pinError: bridge && bridge.pinError ? String(bridge.pinError) : ""
    readonly property var accounts: bridge && bridge.accounts ? bridge.accounts : []
    readonly property var followed: bridge && bridge.followed ? bridge.followed : []
    readonly property var searchHistory: bridge && bridge.searchHistory ? bridge.searchHistory : []
    readonly property var searchResults: bridge && bridge.searchResults ? bridge.searchResults : []
    readonly property bool searchBusy: bridge && bridge.searchBusy ? true : false
    readonly property bool accountRefreshBusy: bridge && bridge.accountRefreshBusy ? true : false
    readonly property bool detectionBusy: bridge && bridge.detectionBusy ? true : false
    readonly property bool qrBusy: bridge && bridge.qrBusy ? true : false
    readonly property var currentMatch: bridge && bridge.currentMatch ? bridge.currentMatch : ({})
    readonly property bool gameDetected: bridge && bridge.gameDetected ? true : false
    readonly property string viewMode: bridge && bridge.viewMode ? String(bridge.viewMode) : "grid"
    readonly property var selectedAccount: bridge && bridge.selectedAccount ? bridge.selectedAccount : ({})
    readonly property var settings: bridge && bridge.settings ? bridge.settings : ({})
    readonly property var pendingQr: bridge && bridge.pendingQr ? bridge.pendingQr : ({})
    readonly property bool qrPromptOpen: bridge && bridge.qrPromptOpen ? true : false
    readonly property string toastText: bridge && bridge.toastText ? String(bridge.toastText) : ""
    readonly property bool detailOpen: accountId(selectedAccount).length > 0
    readonly property bool reduceMotion: settingBool("reduceMotion", false)
    readonly property int motionFast: reduceMotion ? 0 : 140
    readonly property int motionNormal: reduceMotion ? 0 : 220
    readonly property int motionSlow: reduceMotion ? 0 : 320

    function value(object, key, fallback) {
        if (!object || object[key] === undefined || object[key] === null || object[key] === "")
            return fallback
        return object[key]
    }
    function accountId(account) {
        return String(value(account, "id", value(account, "puuid", value(account, "accountId", value(account, "riotId", "")))))
    }
    function accountName(account) {
        var riotId = value(account, "riotId", value(account, "query", null))
        if (riotId !== null) return String(riotId)
        var game = value(account, "gameName", value(account, "name", value(account, "summonerName", "Riot account")))
        var tag = value(account, "tagLine", value(account, "tag", ""))
        return tag ? String(game) + "#" + String(tag) : String(game)
    }
    function gameInfo(account, game) {
        var ranks = value(account, "ranks", [])
        if (ranks && ranks.length !== undefined) {
            var target = String(game).toLowerCase()
            for (var r = 0; r < ranks.length; r++) {
                var rankGame = String(value(ranks[r], "game", "")).toLowerCase()
                if ((target === "league" && (rankGame === "league" || rankGame === "league of legends" || rankGame === "lol")) ||
                    (target === "valorant" && rankGame === "valorant") ||
                    (target === "tft" && rankGame === "tft"))
                    return ranks[r]
            }
            return ({})
        }
        var info = value(account, game, null)
        if (info === null && game === "league") info = value(account, "lol", null)
        if (info === null && game === "valorant") info = value(account, "val", null)
        if (typeof info === "string") return { rank: info }
        return info || ({})
    }
    function rank(account, game) {
        var info = gameInfo(account, game)
        return String(value(info, "tier", value(info, "rank", value(info, "rankName", "Unranked"))))
    }
    function peak(account, game) {
        var info = gameInfo(account, game)
        return String(value(info, "peakRank", value(info, "peak", rank(account, game))))
    }
    function hasTft(account) {
        var ranks = value(account, "ranks", [])
        if (ranks && ranks.length !== undefined) {
            for (var r = 0; r < ranks.length; r++) {
                if (String(value(ranks[r], "game", "")).toLowerCase() === "tft") return true
            }
            return false
        }
        var info = value(account, "tft", null)
        if (info === null || info === undefined) return false
        if (typeof info === "boolean") return info
        return value(info, "played", true) !== false
    }
    function record(account, game) {
        var info = gameInfo(account, game)
        return String(value(info, "rating", value(info, "record", value(info, "lp", value(info, "rr", "—")))))
    }
    function rankIcon(account, game) {
        return String(value(gameInfo(account, game), "icon", ""))
    }
    function dateLabel(account) {
        return String(value(account, "lastGameSince", value(account, "lastGame", "No games yet")))
    }
    function followedCurrentRank(account) {
        return String(value(account, "currentRank", rank(account, "league")))
    }
    function followedPeakRank(account) {
        return String(value(account, "peakRank", peak(account, "league")))
    }
    function matchGameLabel(match) {
        var game = String(value(match, "game", "League of Legends"))
        if (game === "league_of_legends" || game === "league") return "League of Legends"
        if (game === "tft" || game === "teamfight_tactics") return "Teamfight Tactics"
        if (game === "valorant") return "VALORANT"
        return game
    }
    function currentTeams() {
        var teams = value(currentMatch, "teams", [])
        return teams && teams.length !== undefined ? teams : []
    }
    function publicMatchValue(key, fallback) {
        // Game, mode, map and elapsed time are not player identities. Streamer
        // mode must keep these useful facts visible instead of masking the match.
        return String(value(currentMatch, key, fallback))
    }
    function nav(pageName) {
        if (bridge && bridge.navigate) bridge.navigate(pageName)
    }
    function select(account) {
        connectMenuOpen = false
        if (bridge && bridge.selectAccount) bridge.selectAccount(accountId(account))
    }
    function closeDetail() {
        connectMenuOpen = false
        if (bridge && bridge.closeAccount) bridge.closeAccount()
    }
    function submitPin() {
        if (pinDigits.length === 4 && bridge && bridge.submitPin) {
            // Drop the local digit buffer before crossing into Python.  This
            // prevents a rejected/slow unlock attempt from retaining the PIN
            // in the QML object while the controller evaluates it.
            var submittedPin = pinDigits
            pinDigits = ""
            bridge.submitPin(submittedPin)
        }
    }
    function enterPinDigit(digit) {
        if (pinDigits.length >= 4) return
        pinDigits += String(digit)
        if (pinDigits.length === 4) submitPin()
    }
    function clearPinDigit() {
        pinDigits = pinDigits.slice(0, -1)
    }
    function startSearch() {
        if (bridge && bridge.runSearch && searchRiotId.text.trim().length > 0)
            bridge.runSearch(searchRiotId.text.trim(), searchRegion.currentText, searchGame.currentText)
    }
    function autoLockMinutes() {
        var setting = value(settings, "autoLockMinutes", value(settings, "autoLock", 15))
        return Number(setting)
    }
    function settingBool(key, fallback) {
        return Boolean(value(settings, key, fallback))
    }
    function identityLabel(player) {
        // The Windows adapter redacts incognito identities before they reach QML.
        // Preserve that neutral label; never resolve or reconstruct a player name here.
        return String(value(player, "name", "Player"))
    }
    function pageTitle() {
        if (detailOpen) return accountName(selectedAccount)
        if (page === "search") return "Search"
        if (page === "watchlist") return "Watchlist"
        if (page === "current") return "Current match"
        if (page === "settings") return "Settings"
        if (page === "account") return accountName(selectedAccount)
        return "Overview"
    }

    property string pinDigits: ""
    property string riotApiKeyDraft: ""
    property bool addAccountOpen: false
    property bool connectMenuOpen: false
    property bool forgotCodeOpen: false
    property bool forgotCodeFinalOpen: false

    Connections {
        target: window.bridge
        ignoreUnknownSignals: true
        function onPinModeChanged() { window.pinDigits = "" }
        function onPinErrorChanged() { if (window.pinError.length > 0) window.pinDigits = "" }
        function onLockedChanged() { if (window.locked) window.pinDigits = "" }
    }

    FontLoader { id: regularFont; source: "" }

    // Main application surface. Keeping the surface separate lets MultiEffect blur it
    // while the lock and confirmation surfaces remain perfectly sharp.
    Item {
        id: appSurface
        anchors.fill: parent

        Rectangle {
            id: sidebar
            width: 244
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            color: window.panel

            Rectangle { anchors.right: parent.right; width: 1; anchors.top: parent.top; anchors.bottom: parent.bottom; color: window.line }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    Layout.bottomMargin: 36
                    spacing: 10
                    Rectangle {
                        Layout.preferredWidth: 34; Layout.preferredHeight: 34; radius: 10; color: window.textPrimary
                        Text { anchors.centerIn: parent; text: "▲"; color: window.ink; font.pixelSize: 17; font.bold: true }
                    }
                    ColumnLayout {
                        spacing: 1
                        Text { text: "PEAKS"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 15; font.bold: true; font.letterSpacing: 2 }
                        Text { text: "Riot companion"; color: window.textQuiet; font.family: "Segoe UI"; font.pixelSize: 10 }
                    }
                }

                Text { text: "WORKSPACE"; color: window.textQuiet; font.family: "Segoe UI"; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.2; Layout.leftMargin: 13; Layout.bottomMargin: 10 }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    NavItem { label: "Overview"; glyph: "⌂"; pageName: "overview" }
                    NavItem { label: "Search"; glyph: "⌕"; pageName: "search" }
                    NavItem { label: "Watchlist"; glyph: "☆"; pageName: "watchlist" }
                    NavItem {
                        label: window.gameDetected ? "Current match" : "No game detected"
                        glyph: "◉"
                        pageName: "current"
                        enabled: window.gameDetected
                        muted: !window.gameDetected
                    }
                }

                Item { Layout.fillHeight: true }
                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: window.line; Layout.bottomMargin: 10 }
                NavItem { label: "Settings"; glyph: "⚙"; pageName: "settings" }

                Rectangle {
                    Layout.fillWidth: true; Layout.topMargin: 18; Layout.bottomMargin: 8
                    Layout.preferredHeight: 46; radius: 9; color: window.ink; border.color: window.line
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 8
                        Rectangle { Layout.preferredWidth: 25; Layout.preferredHeight: 25; radius: 13; color: "#27313F"; Text { anchors.centerIn: parent; text: "P"; color: window.accent; font.pixelSize: 11; font.bold: true } }
                        ColumnLayout { Layout.fillWidth: true; spacing: 1; Text { text: "Local profile"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 11; elide: Text.ElideRight } Text { text: "Protected on this device"; color: window.textQuiet; font.family: "Segoe UI"; font.pixelSize: 9 } }
                    }
                }
            }
        }

        component NavItem: Item {
            id: navItem
            property string label: ""
            property string glyph: ""
            property string pageName: ""
            property bool muted: false
            property bool active: window.page === pageName
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            opacity: enabled ? 1 : 0.5
            Rectangle { anchors.fill: parent; radius: 8; color: navItem.active ? "#222831" : (hover.containsMouse && navItem.enabled ? window.panelHover : "transparent") }
            Rectangle { width: 3; height: 19; radius: 2; anchors.left: parent.left; anchors.leftMargin: 0; anchors.verticalCenter: parent.verticalCenter; color: navItem.active ? window.accent : "transparent" }
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 10; spacing: 12
                Text { text: navItem.glyph; color: navItem.active ? window.accent : (navItem.muted ? window.textQuiet : window.textSecondary); font.family: "Segoe UI Symbol"; font.pixelSize: 17; horizontalAlignment: Text.AlignHCenter; Layout.preferredWidth: 18 }
                Text { text: navItem.label; color: navItem.active ? window.textPrimary : (navItem.muted ? window.textQuiet : window.textSecondary); font.family: "Segoe UI"; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
            }
            MouseArea { id: hover; anchors.fill: parent; enabled: navItem.enabled; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: window.nav(navItem.pageName) }
        }

        Item {
            id: content
            anchors.left: sidebar.right; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom
            anchors.margins: 0

            Rectangle {
                anchors.fill: parent
                color: window.ink
                gradient: Gradient {
                    GradientStop { position: 0; color: "#0B0D11" }
                    GradientStop { position: 0.5; color: window.ink }
                    GradientStop { position: 1; color: "#0A0B0E" }
                }
            }

            RowLayout {
                id: topbar
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.leftMargin: 42; anchors.rightMargin: 42; anchors.topMargin: 28
                height: 40; spacing: 12
                Text { text: window.pageTitle(); color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 25; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                Text { visible: window.page === "overview"; text: "Updated just now"; color: window.textQuiet; font.family: "Segoe UI"; font.pixelSize: 11 }
                ToolButton {
                    id: refreshButton
                    visible: window.page === "overview"
                    enabled: !window.accountRefreshBusy
                    text: "↻"; font.pixelSize: 20; palette.buttonText: window.textSecondary
                    onClicked: if (window.bridge && window.bridge.refreshAccounts) window.bridge.refreshAccounts()
                    background: Rectangle { radius: 8; color: refreshButton.hovered ? window.panelHover : "transparent" }
                }
                ToolButton {
                    text: "?"; font.pixelSize: 13; palette.buttonText: window.textSecondary
                    background: Rectangle { width: 28; height: 28; radius: 14; border.color: window.line; color: "transparent" }
                }
            }

            Item {
                id: pageArea
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: topbar.bottom; anchors.bottom: parent.bottom
                anchors.leftMargin: 42; anchors.rightMargin: 42; anchors.topMargin: 28; anchors.bottomMargin: 32

                // Overview -----------------------------------------------------------------
                Item {
                    id: overviewPage
                    anchors.fill: parent
                    property bool activePage: window.page === "overview"
                    visible: activePage || opacity > 0.001
                    enabled: activePage
                    opacity: activePage ? 1 : 0
                    property real transitionY: activePage ? 0 : 8
                    transform: Translate { y: overviewPage.transitionY }
                    Behavior on opacity { NumberAnimation { duration: window.motionNormal; easing.type: Easing.OutCubic } }
                    Behavior on transitionY { NumberAnimation { duration: window.motionNormal; easing.type: Easing.OutCubic } }
                    ColumnLayout {
                        anchors.fill: parent; spacing: 20
                        RowLayout {
                            Layout.fillWidth: true; Layout.preferredHeight: 40; spacing: 10
                            ColumnLayout { Layout.fillWidth: true; spacing: 2; Text { text: "Your accounts"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 15; font.bold: true } Text { text: window.accounts.length + " connected"; color: window.textSecondary; font.family: "Segoe UI"; font.pixelSize: 11 } }
                            IconToggle { glyph: "▦"; active: window.viewMode !== "list"; onClicked: if (window.bridge && window.bridge.setViewMode) window.bridge.setViewMode("grid") }
                            IconToggle { glyph: "☷"; active: window.viewMode === "list"; onClicked: if (window.bridge && window.bridge.setViewMode) window.bridge.setViewMode("list") }
                            Button {
                                text: "+  Add account"; font.family: "Segoe UI"; font.pixelSize: 11; palette.buttonText: window.ink
                                leftPadding: 15; rightPadding: 15; background: Rectangle { radius: 8; color: window.textPrimary }
                                onClicked: window.addAccountOpen = true
                            }
                        }
                        Item {
                            id: accountsViewport
                            Layout.fillWidth: true; Layout.fillHeight: true
                            EmptyState { visible: window.accounts.length === 0; title: "No accounts yet"; message: "Connect a Riot account to see ranks, peaks and recent games."; actionText: "Add your first account"; onAction: window.addAccountOpen = true }
                            GridView {
                                id: accountGrid
                                anchors.fill: parent; visible: window.accounts.length > 0 && window.viewMode !== "list"; clip: true
                                cellWidth: Math.max(285, Math.floor(width / Math.max(1, Math.floor(width / 330))))
                                cellHeight: 228; model: window.accounts
                                delegate: AccountCard { account: modelData; cardWidth: accountGrid.cellWidth - 12 }
                            }
                            ListView {
                                id: accountList
                                anchors.fill: parent; visible: window.accounts.length > 0 && window.viewMode === "list"; clip: true; spacing: 8; model: window.accounts
                                delegate: AccountRow { account: modelData }
                            }
                            Item {
                                anchors.fill: parent
                                visible: window.accountRefreshBusy
                                z: 5
                                GridView {
                                    id: refreshCardSkeletons
                                    anchors.fill: parent
                                    visible: window.viewMode !== "list"
                                    cellWidth: Math.max(285, Math.floor(width / Math.max(1, Math.floor(width / 330))))
                                    cellHeight: 228
                                    model: 6
                                    delegate: SkeletonCard { cardWidth: refreshCardSkeletons.cellWidth - 12; active: window.accountRefreshBusy }
                                }
                                ListView {
                                    id: refreshRowSkeletons
                                    anchors.fill: parent
                                    visible: window.viewMode === "list"
                                    spacing: 8
                                    model: 6
                                    delegate: SkeletonRow { width: refreshRowSkeletons.width; active: window.accountRefreshBusy }
                                }
                            }
                        }
                    }
                }

                // Account detail ------------------------------------------------------------
                Item {
                    id: detailPage
                    anchors.fill: parent
                    property bool activePage: window.detailOpen
                    visible: activePage || opacity > 0.001
                    enabled: activePage
                    opacity: activePage ? 1 : 0
                    property real transitionY: activePage ? 0 : 8
                    transform: Translate { y: detailPage.transitionY }
                    z: 8
                    Behavior on opacity { NumberAnimation { duration: window.motionNormal; easing.type: Easing.OutCubic } }
                    Behavior on transitionY { NumberAnimation { duration: window.motionNormal; easing.type: Easing.OutCubic } }
                    Rectangle { anchors.fill: parent; color: window.ink }
                    Flickable { anchors.fill: parent; contentWidth: width; contentHeight: detailColumn.implicitHeight + 20; clip: true
                        ColumnLayout { id: detailColumn; width: parent.width; spacing: 20
                            RowLayout { Layout.fillWidth: true; Layout.preferredHeight: 34; spacing: 10
                                ToolButton { text: "‹"; font.pixelSize: 27; palette.buttonText: window.textSecondary; background: Rectangle { color: "transparent" } onClicked: window.closeDetail() }
                                ColumnLayout { Layout.fillWidth: true; spacing: 1; Text { text: window.accountName(window.selectedAccount); color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 17; font.bold: true } Text { text: "Account details"; color: window.textQuiet; font.family: "Segoe UI"; font.pixelSize: 10 } }
                                RowLayout { visible: Boolean(window.value(window.selectedAccount, "owned", false)); spacing: 0
                                    Button { text: window.qrBusy ? "Connecting…" : "Connect"; enabled: !window.qrBusy; font.family: "Segoe UI"; font.pixelSize: 11; palette.buttonText: window.ink; leftPadding: 16; rightPadding: 16; background: Rectangle { radius: 7; color: window.accent } onClicked: { window.connectMenuOpen = false; if (window.bridge && window.bridge.scanRiotQr) window.bridge.scanRiotQr(window.accountId(window.selectedAccount)) } }
                                    ToolButton { text: "⌄"; font.pixelSize: 16; palette.buttonText: window.ink; background: Rectangle { radius: 7; color: window.accent } onClicked: window.connectMenuOpen = !window.connectMenuOpen }
                                }
                                Text { visible: !Boolean(window.value(window.selectedAccount, "owned", false)); text: "History only"; color: window.textQuiet; font.family: "Segoe UI"; font.pixelSize: 10 }
                            }
                            Rectangle { visible: window.connectMenuOpen && Boolean(window.value(window.selectedAccount, "owned", false)); Layout.alignment: Qt.AlignRight; Layout.preferredWidth: 290; Layout.preferredHeight: 174; radius: 9; color: window.panelRaised; border.color: window.line; z: 4
                                Column { anchors.fill: parent; anchors.margins: 6; spacing: 2
                                    MenuAction { label: "Scan Riot Client QR"; glyph: "⌁"; onTriggered: { window.connectMenuOpen = false; if (window.bridge && window.bridge.scanRiotQr) window.bridge.scanRiotQr(window.accountId(window.selectedAccount)) } }
                                    MenuAction { label: "Paste QR screenshot"; glyph: "▣"; onTriggered: { window.connectMenuOpen = false; if (window.bridge && window.bridge.pasteQrScreenshot) window.bridge.pasteQrScreenshot(window.accountId(window.selectedAccount)) } }
                                    MenuAction { label: "Copy TOTP"; glyph: "⧉"; onTriggered: { window.connectMenuOpen = false; if (window.bridge && window.bridge.copyTotp) window.bridge.copyTotp(window.accountId(window.selectedAccount)) } }
                                    MenuAction { label: "Import current Riot session (Windows)"; glyph: "⇩"; onTriggered: { window.connectMenuOpen = false; if (window.bridge && window.bridge.importCurrentRiotSession) window.bridge.importCurrentRiotSession(window.accountId(window.selectedAccount)) } }
                                }
                            }
                            RowLayout { Layout.fillWidth: true; spacing: 12
                                RankPanel { title: "LEAGUE OF LEGENDS"; rankText: window.rank(window.selectedAccount, "league"); detailText: window.record(window.selectedAccount, "league"); iconSource: window.rankIcon(window.selectedAccount, "league"); accentColor: "#C8945E" }
                                RankPanel { title: "VALORANT"; rankText: window.rank(window.selectedAccount, "valorant"); detailText: window.record(window.selectedAccount, "valorant"); iconSource: window.rankIcon(window.selectedAccount, "valorant"); accentColor: "#E98591" }
                                RankPanel { visible: window.hasTft(window.selectedAccount); title: "TEAMFIGHT TACTICS"; rankText: window.rank(window.selectedAccount, "tft"); detailText: window.record(window.selectedAccount, "tft"); iconSource: window.rankIcon(window.selectedAccount, "tft"); accentColor: "#8DABEA" }
                            }
                            Text { text: "Recent match history"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 15; font.bold: true; Layout.topMargin: 8 }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 54; radius: 8; color: window.panel; border.color: window.line
                                RowLayout { anchors.fill: parent; anchors.leftMargin: 15; anchors.rightMargin: 15; Text { text: "GAME"; color: window.textQuiet; font.pixelSize: 9; font.bold: true; Layout.preferredWidth: 145 } Text { text: "RESULT"; color: window.textQuiet; font.pixelSize: 9; font.bold: true; Layout.preferredWidth: 100 } Text { text: "MODE"; color: window.textQuiet; font.pixelSize: 9; font.bold: true; Layout.preferredWidth: 130 } Text { text: "PLAYED"; color: window.textQuiet; font.pixelSize: 9; font.bold: true; Layout.fillWidth: true } }
                            }
                            Repeater { model: window.value(window.selectedAccount, "matches", window.value(window.selectedAccount, "matchHistory", [])); delegate: MatchRow { match: modelData } }
                            EmptyState { visible: window.value(window.selectedAccount, "matches", window.value(window.selectedAccount, "matchHistory", [])).length === 0; Layout.fillWidth: true; Layout.preferredHeight: 160; title: "No match history"; message: "Recent games will appear here when the account is synced." }
                        }
                    }
                }

                // Search -------------------------------------------------------------------
                Item {
                    id: searchPage
                    anchors.fill: parent
                    property bool activePage: window.page === "search"
                    visible: activePage || opacity > 0.001
                    enabled: activePage
                    opacity: activePage ? 1 : 0
                    property real transitionY: activePage ? 0 : 8
                    transform: Translate { y: searchPage.transitionY }
                    Behavior on opacity { NumberAnimation { duration: window.motionNormal; easing.type: Easing.OutCubic } }
                    Behavior on transitionY { NumberAnimation { duration: window.motionNormal; easing.type: Easing.OutCubic } }
                    Flickable { anchors.fill: parent; contentWidth: width; contentHeight: searchColumn.implicitHeight + 20; clip: true
                        ColumnLayout { id: searchColumn; width: parent.width; spacing: 22
                            Text { text: "Find a player"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 15; font.bold: true }
                            RowLayout { Layout.fillWidth: true; spacing: 8
                                ComboBox { id: searchGame; model: ["League", "Valorant", "TFT"]; currentIndex: 0; Layout.preferredWidth: 150; font.family: "Segoe UI"; font.pixelSize: 11; background: Rectangle { radius: 8; color: window.panelRaised; border.color: window.line } contentItem: Text { leftPadding: 13; text: searchGame.displayText; color: window.textPrimary; font: searchGame.font; verticalAlignment: Text.AlignVCenter } }
                                TextField { id: searchRiotId; Layout.fillWidth: true; placeholderText: "Riot ID#Tag"; font.family: "Segoe UI"; font.pixelSize: 12; color: window.textPrimary; placeholderTextColor: window.textQuiet; selectByMouse: true; onAccepted: window.startSearch(); background: Rectangle { radius: 8; color: window.panelRaised; border.color: parent.activeFocus ? window.accentStrong : window.line } }
                                ComboBox { id: searchRegion; model: ["EUW", "NA", "EUNE", "KR", "BR", "LAN", "LAS", "OCE", "TR", "JP", "SEA"]; currentIndex: 0; Layout.preferredWidth: 142; font.family: "Segoe UI"; font.pixelSize: 11; background: Rectangle { radius: 8; color: window.panelRaised; border.color: window.line } contentItem: Text { leftPadding: 13; text: searchRegion.displayText; color: window.textPrimary; font: searchRegion.font; verticalAlignment: Text.AlignVCenter } }
                                Button { text: window.searchBusy ? "Searching…" : "Search"; enabled: !window.searchBusy; font.family: "Segoe UI"; font.pixelSize: 11; palette.buttonText: window.ink; leftPadding: 19; rightPadding: 19; background: Rectangle { radius: 8; color: window.accent } onClicked: window.startSearch() }
                            }
                            Text { text: "Search history"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 14; font.bold: true; Layout.topMargin: 7 }
                            RowLayout { Layout.fillWidth: true; spacing: 7
                                Repeater { model: window.searchHistory; delegate: Rectangle { height: 30; width: historyLabel.implicitWidth + 27; radius: 15; color: window.panelRaised; border.color: window.line; Text { id: historyLabel; anchors.centerIn: parent; text: typeof modelData === "string" ? modelData : String(window.value(modelData, "query", window.accountName(modelData))); color: window.textSecondary; font.family: "Segoe UI"; font.pixelSize: 10 } } }
                                Text { visible: window.searchHistory.length === 0; text: "Your searches will be saved here"; color: window.textQuiet; font.family: "Segoe UI"; font.pixelSize: 11 }
                                Item { Layout.fillWidth: true }
                                Button { visible: window.searchHistory.length > 0; text: "Clear"; flat: true; font.family: "Segoe UI"; font.pixelSize: 10; palette.buttonText: window.textSecondary; onClicked: if (window.bridge && window.bridge.clearSearchHistory) window.bridge.clearSearchHistory() }
                            }
                            Text { text: "Results"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 14; font.bold: true; Layout.topMargin: 8 }
                            EmptyState { visible: window.searchResults.length === 0 && !window.searchBusy; Layout.fillWidth: true; Layout.preferredHeight: 190; title: "Search for a player"; message: "Look up a Riot ID to see their rank and recent games." }
                            ColumnLayout {
                                visible: window.searchBusy
                                Layout.fillWidth: true
                                spacing: 8
                                SkeletonRow { Layout.fillWidth: true; active: window.searchBusy }
                                SkeletonRow { Layout.fillWidth: true; active: window.searchBusy }
                                SkeletonRow { Layout.fillWidth: true; active: window.searchBusy }
                            }
                            Repeater { visible: !window.searchBusy; model: window.searchResults; delegate: SearchResultRow { result: modelData } }
                        }
                    }
                }

                // Watchlist ----------------------------------------------------------------
                Item {
                    id: followedPage
                    anchors.fill: parent
                    property bool activePage: window.page === "watchlist"
                    visible: activePage || opacity > 0.001
                    enabled: activePage
                    opacity: activePage ? 1 : 0
                    property real transitionY: activePage ? 0 : 8
                    transform: Translate { y: followedPage.transitionY }
                    Behavior on opacity { NumberAnimation { duration: window.motionNormal; easing.type: Easing.OutCubic } }
                    Behavior on transitionY { NumberAnimation { duration: window.motionNormal; easing.type: Easing.OutCubic } }
                    ColumnLayout { anchors.fill: parent; spacing: 18
                        RowLayout { Layout.fillWidth: true; Text { text: "Watchlist"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 15; font.bold: true; Layout.fillWidth: true } Text { text: window.followed.length + " watched"; color: window.textSecondary; font.family: "Segoe UI"; font.pixelSize: 11 } }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 48; radius: 8; color: window.panel; border.color: window.line; RowLayout { anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; Text { text: "PLAYER"; color: window.textQuiet; font.pixelSize: 9; font.bold: true; Layout.fillWidth: true } Text { text: "LAST GAME SINCE"; color: window.textQuiet; font.pixelSize: 9; font.bold: true; Layout.preferredWidth: 160 } Text { text: "RANK / PEAK"; color: window.textQuiet; font.pixelSize: 9; font.bold: true; Layout.preferredWidth: 190 } Item { Layout.preferredWidth: 25 } } }
                        ListView { Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 8; model: window.followed; delegate: FollowedRow { account: modelData } }
                        EmptyState { visible: window.followed.length === 0; Layout.fillWidth: true; Layout.fillHeight: true; title: "Your watchlist is empty"; message: "Search for a player and choose Watch to keep their progress close." }
                    }
                }

                // Current match ------------------------------------------------------------
                Item {
                    id: currentPage
                    anchors.fill: parent
                    property bool activePage: window.page === "current"
                    visible: activePage || opacity > 0.001
                    enabled: activePage
                    opacity: activePage ? 1 : 0
                    property real transitionY: activePage ? 0 : 8
                    transform: Translate { y: currentPage.transitionY }
                    Behavior on opacity { NumberAnimation { duration: window.motionNormal; easing.type: Easing.OutCubic } }
                    Behavior on transitionY { NumberAnimation { duration: window.motionNormal; easing.type: Easing.OutCubic } }
                    EmptyState { visible: !window.gameDetected && !window.detectionBusy; anchors.centerIn: parent; title: "No game detected"; message: "Start a League of Legends, TFT or VALORANT game to see the lobby here." }
                    ColumnLayout {
                        visible: window.detectionBusy && !window.gameDetected
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        spacing: 20
                        SkeletonBlock { Layout.preferredWidth: 210; Layout.preferredHeight: 22; active: window.detectionBusy && !window.gameDetected }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            SkeletonBlock { Layout.fillWidth: true; Layout.preferredHeight: 220; active: window.detectionBusy && !window.gameDetected }
                            SkeletonBlock { Layout.fillWidth: true; Layout.preferredHeight: 220; active: window.detectionBusy && !window.gameDetected }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            SkeletonBlock { Layout.fillWidth: true; Layout.preferredHeight: 64; active: window.detectionBusy && !window.gameDetected }
                            SkeletonBlock { Layout.fillWidth: true; Layout.preferredHeight: 64; active: window.detectionBusy && !window.gameDetected }
                            SkeletonBlock { Layout.fillWidth: true; Layout.preferredHeight: 64; active: window.detectionBusy && !window.gameDetected }
                        }
                    }
                    Flickable { visible: window.gameDetected; anchors.fill: parent; contentWidth: width; contentHeight: currentColumn.implicitHeight + 20; clip: true
                        ColumnLayout { id: currentColumn; width: parent.width; spacing: 20
                            RowLayout { Layout.fillWidth: true; Layout.preferredHeight: 40
                                ColumnLayout { Layout.fillWidth: true; spacing: 2; Text { text: window.publicMatchValue("title", window.publicMatchValue("game", "Current game")); color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 17; font.bold: true } Text { text: window.publicMatchValue("mode", "Match in progress"); color: window.textSecondary; font.family: "Segoe UI"; font.pixelSize: 11 } }
                                Rectangle { visible: Boolean(window.value(window.currentMatch, "streamerMode", false)); radius: 5; color: "#242A34"; Layout.preferredWidth: privacyText.implicitWidth + 18; Layout.preferredHeight: 24; Text { id: privacyText; anchors.centerIn: parent; text: "◉  Streamer mode"; color: window.accent; font.family: "Segoe UI"; font.pixelSize: 10 } }
                            }
                            RowLayout { visible: window.currentTeams().length > 0; Layout.fillWidth: true; spacing: 12; MatchTeam { team: window.currentTeams().length > 0 ? window.currentTeams()[0] : ({}) } MatchTeam { team: window.currentTeams().length > 1 ? window.currentTeams()[1] : ({}) } }
                            Rectangle { visible: window.currentTeams().length === 0; Layout.fillWidth: true; Layout.preferredHeight: 112; radius: 11; color: window.panel; border.color: window.line; RowLayout { anchors.fill: parent; anchors.margins: 20; spacing: 22; Text { text: "VS"; color: window.accent; font.family: "Segoe UI"; font.pixelSize: 20; font.bold: true; Layout.preferredWidth: 42 } ColumnLayout { Layout.fillWidth: true; spacing: 5; Text { text: "Your team"; color: window.textSecondary; font.pixelSize: 10 } Text { text: window.publicMatchValue("allyNames", "Players hidden"); color: window.textPrimary; font.pixelSize: 14; font.bold: true; elide: Text.ElideRight } } Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: window.line } ColumnLayout { Layout.fillWidth: true; spacing: 5; Text { text: "Opposing team"; color: window.textSecondary; font.pixelSize: 10 } Text { text: window.publicMatchValue("enemyNames", "Players hidden"); color: window.textPrimary; font.pixelSize: 14; font.bold: true; elide: Text.ElideRight } } } }
                            RowLayout { Layout.fillWidth: true; spacing: 12; MatchStat { label: "QUEUE"; valueText: window.publicMatchValue("queue", window.publicMatchValue("mode", "—")) } MatchStat { label: "MAP"; valueText: window.publicMatchValue("map", "—") } MatchStat { label: "ELAPSED"; valueText: window.publicMatchValue("elapsed", window.publicMatchValue("startedAt", "—")) } }
                        }
                    }
                }

                // Settings -----------------------------------------------------------------
                Item {
                    id: settingsPage
                    anchors.fill: parent
                    property bool activePage: window.page === "settings"
                    visible: activePage || opacity > 0.001
                    enabled: activePage
                    opacity: activePage ? 1 : 0
                    property real transitionY: activePage ? 0 : 8
                    transform: Translate { y: settingsPage.transitionY }
                    Behavior on opacity { NumberAnimation { duration: window.motionNormal; easing.type: Easing.OutCubic } }
                    Behavior on transitionY { NumberAnimation { duration: window.motionNormal; easing.type: Easing.OutCubic } }
                    Flickable { anchors.fill: parent; contentWidth: width; contentHeight: settingsColumn.implicitHeight + 20; clip: true
                        ColumnLayout { id: settingsColumn; width: parent.width; spacing: 12
                            Text { text: "Preferences"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 15; font.bold: true; Layout.bottomMargin: 4 }
                            SettingRow { title: "Auto-lock"; description: "Lock Peaks after a period of inactivity."; control: ComboBox { id: autoLockCombo; model: ["1 minute", "5 minutes", "15 minutes", "30 minutes", "Never"]; currentIndex: [1,5,15,30,0].indexOf(window.autoLockMinutes()); Layout.preferredWidth: 135; font.family: "Segoe UI"; font.pixelSize: 10; onActivated: { var values = [1,5,15,30,0]; if (window.bridge && window.bridge.setAutoLock) window.bridge.setAutoLock(values[currentIndex]) } background: Rectangle { radius: 7; color: window.panelRaised; border.color: window.line } contentItem: Text { leftPadding: 11; text: autoLockCombo.displayText; color: window.textPrimary; font: autoLockCombo.font; verticalAlignment: Text.AlignVCenter } } }
                            SettingRow { title: "Reduce motion"; description: "Use fewer transitions and visual effects."; control: Switch { checked: window.settingBool("reduceMotion", false); onToggled: if (window.bridge && window.bridge.setReduceMotion) window.bridge.setReduceMotion(checked) } }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: window.line; Layout.topMargin: 20; Layout.bottomMargin: 12 }
                            Text { text: "Security"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 15; font.bold: true; Layout.bottomMargin: 4 }
                            SettingRow { title: "Local passcode"; description: window.hasPasscode ? "A four-digit code protects this device." : "Set a four-digit code during first launch."; control: Text { text: window.hasPasscode ? "Enabled" : "First launch"; color: window.good; font.family: "Segoe UI"; font.pixelSize: 10; font.bold: true; horizontalAlignment: Text.AlignRight; verticalAlignment: Text.AlignVCenter } }
                            Button { text: "Lock now"; Layout.alignment: Qt.AlignLeft; Layout.topMargin: 12; font.family: "Segoe UI"; font.pixelSize: 11; palette.buttonText: window.danger; leftPadding: 16; rightPadding: 16; background: Rectangle { radius: 7; color: "#24171B"; border.color: "#543039" } onClicked: if (window.bridge && window.bridge.lockNow) window.bridge.lockNow() }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: window.line; Layout.topMargin: 20; Layout.bottomMargin: 12 }
                            Text { text: "Integrations"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 15; font.bold: true; Layout.bottomMargin: 2 }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 104; radius: 9; color: window.panel; border.color: window.line
                                ColumnLayout { anchors.fill: parent; anchors.margins: 16; spacing: 8
                                    RowLayout { Layout.fillWidth: true; Text { text: "Riot Developer API key"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true } Text { text: "OPTIONAL"; color: window.textQuiet; font.family: "Segoe UI"; font.pixelSize: 8; font.bold: true } }
                                    RowLayout { Layout.fillWidth: true; spacing: 8
                                        TextField { id: riotApiKeyField; Layout.fillWidth: true; placeholderText: "Paste an API key to enable live remote search"; echoMode: TextInput.Password; font.family: "Segoe UI"; font.pixelSize: 10; color: window.textPrimary; placeholderTextColor: window.textQuiet; selectByMouse: true; background: Rectangle { radius: 7; color: window.ink; border.color: parent.activeFocus ? window.accentStrong : window.line } }
                                        Button { text: "Save"; font.family: "Segoe UI"; font.pixelSize: 10; palette.buttonText: window.ink; leftPadding: 14; rightPadding: 14; background: Rectangle { radius: 7; color: window.accent } onClicked: { if (window.bridge && window.bridge.setRiotApiKey) window.bridge.setRiotApiKey(riotApiKeyField.text); riotApiKeyField.clear() } }
                                    }
                                    Text { text: "An official Riot Developer key enables live remote search. Peaks encrypts it locally and keeps the machine key in the OS keychain when available; the key is never shown after saving."; color: window.textSecondary; font.family: "Segoe UI"; font.pixelSize: 9; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                }
                            }
                        }
                    }
                }
            }
        }
        Rectangle {
            id: qrLoadingOverlay
            anchors.centerIn: parent
            width: 300
            height: 86
            radius: 12
            color: window.panelRaised
            border.color: window.line
            visible: window.qrBusy && !window.qrPromptOpen
            opacity: visible ? 1 : 0
            z: 15
            Behavior on opacity { NumberAnimation { duration: window.motionFast; easing.type: Easing.OutCubic } }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 17
                anchors.rightMargin: 17
                spacing: 12
                SkeletonBlock { Layout.preferredWidth: 44; Layout.preferredHeight: 44; radius: 10; active: window.qrBusy }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text { text: "Connecting securely"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 12; font.bold: true }
                    Text { text: "Reading the Riot Client QR…"; color: window.textSecondary; font.family: "Segoe UI"; font.pixelSize: 10 }
                }
            }
        }
    }

    // Blurring the complete app surface preserves the context of the page without
    // exposing account names or ranks while the passcode view is active.
    MultiEffect {
        anchors.fill: appSurface
        source: appSurface
        visible: window.locked || !window.hasPasscode
        blurEnabled: visible
        blur: 1.0
        blurMax: 32
        brightness: -0.16
    }
    Rectangle {
        anchors.fill: parent
        visible: true
        color: "#050608"
        opacity: window.locked || !window.hasPasscode ? 0.72 : 0
        z: 20
        Behavior on opacity { NumberAnimation { duration: window.motionSlow; easing.type: Easing.OutCubic } }
    }

    // First-run setup and unlock ------------------------------------------------------------
    Item {
        id: lockOverlay
        anchors.fill: parent
        property bool lockActive: window.locked || !window.hasPasscode
        visible: true
        enabled: lockActive
        opacity: lockActive ? 1 : 0
        focus: enabled
        Behavior on opacity { NumberAnimation { duration: window.motionSlow; easing.type: Easing.OutCubic } }
        onEnabledChanged: if (enabled) forceActiveFocus()
        Keys.onPressed: function(event) {
            if (!enabled) return
            if (event.key >= Qt.Key_0 && event.key <= Qt.Key_9) {
                window.enterPinDigit(event.text)
                event.accepted = true
            } else if (event.key === Qt.Key_Backspace || event.key === Qt.Key_Delete) {
                window.clearPinDigit()
                event.accepted = true
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                window.submitPin()
                event.accepted = true
            }
        }
        z: 21
        ColumnLayout {
            anchors.centerIn: parent
            width: Math.min(360, parent.width - 48)
            spacing: 0
            Item {
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 54
                Layout.preferredHeight: 54
                Rectangle { anchors.fill: parent; radius: 16; color: window.textPrimary }
                Rectangle { width: 16; height: 16; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 25; radius: 8; color: "transparent"; border.color: window.ink; border.width: 4 }
                Rectangle { id: lockBody; width: 23; height: 18; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 11; radius: 4; color: window.ink }
                Rectangle { width: 3; height: 6; anchors.centerIn: lockBody; radius: 1.5; color: window.textPrimary }
            }
            Text { Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 22; text: window.pinMode === "confirm" ? "Confirm passcode" : (window.hasPasscode ? "Welcome back" : "Secure your Peaks"); color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 24; font.bold: true }
            Text { Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 8; text: window.pinMode === "confirm" ? "Enter the same four digits once more." : (window.hasPasscode ? "Enter your four-digit passcode to continue." : "Create a four-digit passcode for this device."); color: window.textSecondary; font.family: "Segoe UI"; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Row { Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 27; spacing: 14; Repeater { model: 4; delegate: Rectangle { width: 13; height: 13; radius: 7; color: index < window.pinDigits.length ? window.accent : "#3E424A"; border.color: index < window.pinDigits.length ? window.accent : window.line; scale: index < window.pinDigits.length ? 1.14 : 1; Behavior on color { ColorAnimation { duration: window.motionFast } } Behavior on border.color { ColorAnimation { duration: window.motionFast } } Behavior on scale { NumberAnimation { duration: window.motionFast; easing.type: Easing.OutBack } } } } }
            Text { Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 14; text: window.pinError; color: window.danger; font.family: "Segoe UI"; font.pixelSize: 11; visible: text.length > 0 }
        }

        // Keyboard input remains active through lockOverlay.Keys above. Keeping the
        // recovery affordance outside the centered stack leaves the passcode prompt
        // calm and uncluttered while making it reachable from any window size.
        Button {
            visible: window.locked && window.hasPasscode
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.rightMargin: 28
            anchors.bottomMargin: 22
            text: "Forgot your code?"
            flat: true
            font.family: "Segoe UI"
            font.pixelSize: 11
            palette.buttonText: window.textSecondary
            opacity: hovered ? 1.0 : 0.76
            background: Rectangle { color: "transparent" }
            onClicked: {
                window.forgotCodeOpen = true
                forgotCodeFirst.open()
            }
        }
    }

    // Recovery is intentionally a two-step, explicit destructive action. A
    // forgotten four-digit code cannot be recovered without weakening the local
    // vault boundary, so resetApplication returns Peaks to first-launch state.
    Popup {
        id: forgotCodeFirst
        x: Math.round((window.width - width) / 2)
        y: Math.round((window.height - height) / 2)
        width: Math.min(470, window.width - 44)
        height: 272
        modal: true
        dim: true
        closePolicy: Popup.NoAutoClose
        enter: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: window.motionFast; easing.type: Easing.OutCubic }
                NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: window.motionNormal; easing.type: Easing.OutBack }
            }
        }
        exit: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 1; to: 0; duration: window.motionFast; easing.type: Easing.InCubic }
                NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: window.motionFast; easing.type: Easing.InCubic }
            }
        }
        onClosed: {
            window.forgotCodeOpen = false
            lockOverlay.forceActiveFocus()
        }
        background: Rectangle { radius: 13; color: window.panelRaised; border.color: window.line }
        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 26
            spacing: 11
            Text { text: "Reset local data?"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 19; font.bold: true }
            Text {
                text: "Peaks cannot recover a forgotten passcode. Resetting the app permanently deletes every account, credential, search, watchlist entry and setting stored on this device."
                color: window.textSecondary
                font.family: "Segoe UI"
                font.pixelSize: 11
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Button {
                    text: "Cancel"
                    Layout.fillWidth: true
                    font.family: "Segoe UI"
                    font.pixelSize: 11
                    palette.buttonText: window.textSecondary
                    background: Rectangle { radius: 8; color: "transparent"; border.color: window.line }
                    onClicked: forgotCodeFirst.close()
                }
                Button {
                    text: "I understand — continue"
                    Layout.fillWidth: true
                    font.family: "Segoe UI"
                    font.pixelSize: 11
                    palette.buttonText: window.ink
                    background: Rectangle { radius: 8; color: window.accent }
                    onClicked: {
                        forgotCodeFirst.close()
                        forgotCodeFinal.open()
                    }
                }
            }
        }
    }

    Popup {
        id: forgotCodeFinal
        x: Math.round((window.width - width) / 2)
        y: Math.round((window.height - height) / 2)
        width: Math.min(470, window.width - 44)
        height: 250
        modal: true
        dim: true
        closePolicy: Popup.NoAutoClose
        enter: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: window.motionFast; easing.type: Easing.OutCubic }
                NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: window.motionNormal; easing.type: Easing.OutBack }
            }
        }
        exit: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 1; to: 0; duration: window.motionFast; easing.type: Easing.InCubic }
                NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: window.motionFast; easing.type: Easing.InCubic }
            }
        }
        onClosed: {
            window.forgotCodeFinalOpen = false
            lockOverlay.forceActiveFocus()
        }
        background: Rectangle { radius: 13; color: window.panelRaised; border.color: "#59343B" }
        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 26
            spacing: 11
            Text { text: "There is no way back"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 19; font.bold: true }
            Text {
                text: "This action cannot be undone. Confirming will erase the protected Peaks vault and all locally stored data, then return the app to its initial setup."
                color: window.textSecondary
                font.family: "Segoe UI"
                font.pixelSize: 11
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Button {
                    text: "Keep my data"
                    Layout.fillWidth: true
                    font.family: "Segoe UI"
                    font.pixelSize: 11
                    palette.buttonText: window.textSecondary
                    background: Rectangle { radius: 8; color: "transparent"; border.color: window.line }
                    onClicked: forgotCodeFinal.close()
                }
                Button {
                    text: "Reset Peaks"
                    Layout.fillWidth: true
                    font.family: "Segoe UI"
                    font.pixelSize: 11
                    palette.buttonText: "#FFF5F5"
                    background: Rectangle { radius: 8; color: "#A94B57" }
                    onClicked: {
                        forgotCodeFinal.close()
                        if (window.bridge && window.bridge.resetApplication)
                            window.bridge.resetApplication()
                    }
                }
            }
        }
    }

    // Add account dialog --------------------------------------------------------------------
    Popup {
        id: addAccountPopup
        x: Math.round((window.width - width) / 2); y: Math.round((window.height - height) / 2)
        width: Math.min(460, window.width - 40); height: 420; modal: true; dim: true; visible: window.addAccountOpen
        onClosed: window.addAccountOpen = false
        enter: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: window.motionFast; easing.type: Easing.OutCubic }
                NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: window.motionNormal; easing.type: Easing.OutBack }
            }
        }
        exit: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 1; to: 0; duration: window.motionFast; easing.type: Easing.InCubic }
                NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: window.motionFast; easing.type: Easing.InCubic }
            }
        }
        background: Rectangle { radius: 13; color: window.panelRaised; border.color: window.line }
        contentItem: ColumnLayout { anchors.fill: parent; anchors.margins: 26; spacing: 12
            RowLayout { Layout.fillWidth: true; Text { text: "Add a Riot account"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 18; font.bold: true; Layout.fillWidth: true } ToolButton { text: "×"; font.pixelSize: 21; palette.buttonText: window.textSecondary; onClicked: addAccountPopup.close() } }
            Text { text: "Peaks encrypts credentials locally; the machine key is held by the OS keychain when available."; color: window.textSecondary; font.family: "Segoe UI"; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true; Layout.bottomMargin: 8 }
            TextField { id: addName; placeholderText: "Riot ID / game name"; Layout.fillWidth: true; font.family: "Segoe UI"; color: window.textPrimary; placeholderTextColor: window.textQuiet; background: Rectangle { radius: 8; color: window.ink; border.color: window.line } }
            TextField { id: addTag; placeholderText: "Tag line"; Layout.fillWidth: true; font.family: "Segoe UI"; color: window.textPrimary; placeholderTextColor: window.textQuiet; background: Rectangle { radius: 8; color: window.ink; border.color: window.line } }
            TextField { id: addRegion; placeholderText: "Region (e.g. EUW)"; Layout.fillWidth: true; font.family: "Segoe UI"; color: window.textPrimary; placeholderTextColor: window.textQuiet; background: Rectangle { radius: 8; color: window.ink; border.color: window.line } }
            TextField { id: addTotp; placeholderText: "TOTP secret (optional)"; echoMode: TextInput.Password; Layout.fillWidth: true; font.family: "Segoe UI"; color: window.textPrimary; placeholderTextColor: window.textQuiet; background: Rectangle { radius: 8; color: window.ink; border.color: window.line } }
            Item { Layout.fillHeight: true }
            RowLayout { Layout.fillWidth: true; spacing: 8; Button { text: "Cancel"; Layout.fillWidth: true; font.family: "Segoe UI"; font.pixelSize: 11; palette.buttonText: window.textSecondary; background: Rectangle { radius: 8; color: "transparent"; border.color: window.line } onClicked: addAccountPopup.close() } Button { text: "Add account"; Layout.fillWidth: true; font.family: "Segoe UI"; font.pixelSize: 11; palette.buttonText: window.ink; background: Rectangle { radius: 8; color: window.accent } onClicked: { if (window.bridge && window.bridge.addAccount) window.bridge.addAccount(addName.text, addTag.text, addRegion.text, addTotp.text); addAccountPopup.close(); addName.clear(); addTag.clear(); addRegion.clear(); addTotp.clear() } } }
        }
    }

    // A QR was found, but sign-in is never accepted implicitly. The bridge keeps this
    // dialog open until the user explicitly approves or cancels the pending request.
    Popup {
        id: qrConfirmPopup
        x: Math.round((window.width - width) / 2); y: Math.round((window.height - height) / 2)
        width: Math.min(440, window.width - 40); height: 330; modal: true; dim: true; visible: window.qrPromptOpen
        enter: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: window.motionFast; easing.type: Easing.OutCubic }
                NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: window.motionNormal; easing.type: Easing.OutBack }
            }
        }
        exit: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 1; to: 0; duration: window.motionFast; easing.type: Easing.InCubic }
                NumberAnimation { property: "scale"; from: 1; to: 0.98; duration: window.motionFast; easing.type: Easing.InCubic }
            }
        }
        background: Rectangle { radius: 13; color: window.panelRaised; border.color: window.line }
        contentItem: ColumnLayout { anchors.fill: parent; anchors.margins: 25; spacing: 11
            RowLayout { Layout.fillWidth: true; Text { text: "Approve sign-in?"; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 18; font.bold: true; Layout.fillWidth: true } Text { text: "QR"; color: window.accent; font.family: "Segoe UI"; font.pixelSize: 10; font.bold: true } }
            Text { text: "A Riot Client sign-in is ready. Review the details before allowing it."; color: window.textSecondary; font.family: "Segoe UI"; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true; Layout.bottomMargin: 8 }
            DetailLine { label: "ACCOUNT"; detail: String(window.value(window.pendingQr, "account", window.accountName(window.pendingQr))) }
            DetailLine { label: "LOCATION / DEVICE"; detail: String(window.value(window.pendingQr, "location", window.value(window.pendingQr, "device", "Unknown device"))) }
            DetailLine { label: "TIME"; detail: String(window.value(window.pendingQr, "time", window.value(window.pendingQr, "requested", window.value(window.pendingQr, "createdAt", "Just now")))) }
            Item { Layout.fillHeight: true }
            RowLayout { Layout.fillWidth: true; spacing: 8; Button { text: "Cancel"; Layout.fillWidth: true; font.family: "Segoe UI"; font.pixelSize: 11; palette.buttonText: window.textSecondary; background: Rectangle { radius: 8; color: "transparent"; border.color: window.line } onClicked: { if (window.bridge && window.bridge.confirmQr) window.bridge.confirmQr(false); if (window.bridge && window.bridge.closeQrPrompt) window.bridge.closeQrPrompt() } } Button { text: "Approve"; Layout.fillWidth: true; font.family: "Segoe UI"; font.pixelSize: 11; palette.buttonText: window.ink; background: Rectangle { radius: 8; color: window.accent } onClicked: { if (window.bridge && window.bridge.confirmQr) window.bridge.confirmQr(true) } } }
        }
    }

    Toast { visible: true; opacity: window.toastText.length > 0 ? 1 : 0; text: window.toastText }

    // Lightweight loading primitives.  These deliberately use a single moving
    // rectangle instead of a shader so they stay inexpensive on Windows laptops
    // and become static when Reduce motion is enabled.
    component SkeletonBlock: Rectangle {
        id: skeletonBlock
        property bool active: true
        implicitWidth: 120
        implicitHeight: 18
        radius: 6
        color: "#191D24"
        border.color: "#252A33"
        clip: true
        Rectangle {
            id: sheen
            x: -width
            width: Math.max(34, skeletonBlock.width * 0.34)
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            gradient: Gradient {
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.5; color: "#343B48" }
                GradientStop { position: 1.0; color: "transparent" }
            }
            visible: skeletonBlock.active && !window.reduceMotion
            NumberAnimation on x {
                from: -sheen.width
                to: skeletonBlock.width
                duration: 1_250
                loops: Animation.Infinite
                running: sheen.visible && skeletonBlock.width > 0
            }
        }
    }
    component SkeletonRow: Rectangle {
        id: skeletonRow
        property bool active: true
        implicitHeight: 72
        height: implicitHeight
        radius: 9
        color: window.panel
        border.color: window.line
        RowLayout {
            anchors.fill: parent
            anchors.margins: 14
            spacing: 12
            SkeletonBlock { Layout.preferredWidth: 34; Layout.preferredHeight: 34; radius: 17; active: skeletonRow.active }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 7
                SkeletonBlock { Layout.preferredWidth: 180; Layout.preferredHeight: 10; active: skeletonRow.active }
                SkeletonBlock { Layout.preferredWidth: 112; Layout.preferredHeight: 9; active: skeletonRow.active }
            }
            SkeletonBlock { Layout.preferredWidth: 78; Layout.preferredHeight: 10; active: skeletonRow.active }
        }
    }
    component SkeletonCard: Rectangle {
        id: skeletonCard
        property bool active: true
        property real cardWidth: 320
        width: cardWidth
        height: 216
        radius: 11
        color: window.panel
        border.color: window.line
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 17
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                SkeletonBlock { Layout.preferredWidth: 34; Layout.preferredHeight: 34; radius: 17; active: skeletonCard.active }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    SkeletonBlock { Layout.preferredWidth: 145; Layout.preferredHeight: 10; active: skeletonCard.active }
                    SkeletonBlock { Layout.preferredWidth: 48; Layout.preferredHeight: 8; active: skeletonCard.active }
                }
            }
            SkeletonBlock { Layout.fillWidth: true; Layout.preferredHeight: 27; active: skeletonCard.active }
            SkeletonBlock { Layout.fillWidth: true; Layout.preferredHeight: 27; active: skeletonCard.active }
            SkeletonBlock { Layout.fillWidth: true; Layout.preferredHeight: 27; active: skeletonCard.active }
        }
    }
    component IconToggle: ToolButton {
        property bool active: false
        property string glyph: ""
        text: glyph
        font.family: "Segoe UI Symbol"
        font.pixelSize: 17
        palette.buttonText: active ? window.textPrimary : window.textQuiet
        background: Rectangle { implicitWidth: 32; implicitHeight: 30; radius: 7; color: active ? window.panelRaised : "transparent"; border.color: active ? window.line : "transparent" }
    }
    component EmptyState: ColumnLayout {
        property string title: ""
        property string message: ""
        property string actionText: ""
        signal action()
        id: emptyState
        spacing: 7
        Rectangle { Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: 42; Layout.preferredHeight: 42; radius: 13; color: window.panelRaised; border.color: window.line; Text { anchors.centerIn: parent; text: "⌁"; color: window.accent; font.pixelSize: 21 } }
        Text { Layout.alignment: Qt.AlignHCenter; text: title; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 14; font.bold: true }
        Text { Layout.alignment: Qt.AlignHCenter; Layout.maximumWidth: 360; text: message; color: window.textSecondary; font.family: "Segoe UI"; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap }
        Button { visible: actionText.length > 0; Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 6; text: actionText; font.family: "Segoe UI"; font.pixelSize: 10; palette.buttonText: window.ink; background: Rectangle { radius: 7; color: window.accent } onClicked: emptyState.action() }
    }
    component AccountCard: Rectangle {
        id: accountCard
        property var account: ({})
        property real cardWidth: 320
        width: cardWidth; height: 216; radius: 11; color: window.panel; border.color: cardMouse.containsMouse ? "#3C4654" : window.line
        opacity: 0
        scale: 0.985
        Component.onCompleted: cardReveal.start()
        ParallelAnimation {
            id: cardReveal
            NumberAnimation { target: accountCard; property: "opacity"; from: 0; to: 1; duration: window.motionNormal; easing.type: Easing.OutCubic }
            NumberAnimation { target: accountCard; property: "scale"; from: 0.985; to: 1; duration: window.motionNormal; easing.type: Easing.OutCubic }
        }
        ColumnLayout { anchors.fill: parent; anchors.margins: 17; spacing: 10
            RowLayout { Layout.fillWidth: true; spacing: 10
                Rectangle { Layout.preferredWidth: 34; Layout.preferredHeight: 34; radius: 17; color: "#26303E"; Text { anchors.centerIn: parent; text: window.accountName(account).charAt(0).toUpperCase(); color: window.accent; font.family: "Segoe UI"; font.pixelSize: 13; font.bold: true } }
                ColumnLayout { Layout.fillWidth: true; spacing: 1; Text { text: window.accountName(account); color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true } Text { text: String(window.value(account, "region", "—")); color: window.textQuiet; font.family: "Segoe UI"; font.pixelSize: 10 } }
                Text { text: "⋯"; color: window.textQuiet; font.pixelSize: 17 }
            }
            GameRankLine { game: "LEAGUE OF LEGENDS"; rankText: window.rank(account, "league"); detailText: window.record(account, "league"); iconSource: window.rankIcon(account, "league"); colorAccent: "#C8945E" }
            GameRankLine { game: "VALORANT"; rankText: window.rank(account, "valorant"); detailText: window.record(account, "valorant"); iconSource: window.rankIcon(account, "valorant"); colorAccent: "#E98591" }
            GameRankLine { visible: window.hasTft(account); game: "TFT"; rankText: window.rank(account, "tft"); detailText: window.record(account, "tft"); iconSource: window.rankIcon(account, "tft"); colorAccent: "#8DABEA" }
            Item { Layout.fillHeight: true }
            RowLayout { Layout.fillWidth: true; Text { text: "Peak  " + window.peak(account, "league"); color: window.textQuiet; font.pixelSize: 10; Layout.fillWidth: true } Text { text: "View history  ›"; color: window.accent; font.pixelSize: 10 } }
        }
        MouseArea { id: cardMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: window.select(account) }
    }
    component AccountRow: Rectangle {
        id: accountRow
        property var account: ({})
        width: ListView.view.width; height: 72; radius: 9; color: rowMouse.containsMouse ? window.panelHover : window.panel; border.color: window.line
        opacity: 0
        scale: 0.99
        Component.onCompleted: rowReveal.start()
        ParallelAnimation {
            id: rowReveal
            NumberAnimation { target: accountRow; property: "opacity"; from: 0; to: 1; duration: window.motionFast; easing.type: Easing.OutCubic }
            NumberAnimation { target: accountRow; property: "scale"; from: 0.99; to: 1; duration: window.motionFast; easing.type: Easing.OutCubic }
        }
        RowLayout { anchors.fill: parent; anchors.margins: 14; spacing: 15
            Rectangle { Layout.preferredWidth: 34; Layout.preferredHeight: 34; radius: 17; color: "#26303E"; Text { anchors.centerIn: parent; text: window.accountName(account).charAt(0).toUpperCase(); color: window.accent; font.pixelSize: 13; font.bold: true } }
            ColumnLayout { Layout.preferredWidth: 185; spacing: 2; Text { text: window.accountName(account); color: window.textPrimary; font.pixelSize: 12; font.bold: true } Text { text: String(window.value(account, "region", "—")); color: window.textQuiet; font.pixelSize: 10 } }
            GameRankLine { Layout.fillWidth: true; game: "LEAGUE"; rankText: window.rank(account, "league"); detailText: window.record(account, "league"); iconSource: window.rankIcon(account, "league"); colorAccent: "#C8945E" }
            GameRankLine { Layout.fillWidth: true; game: "VALORANT"; rankText: window.rank(account, "valorant"); detailText: window.record(account, "valorant"); iconSource: window.rankIcon(account, "valorant"); colorAccent: "#E98591" }
            Text { text: "›"; color: window.accent; font.pixelSize: 18 }
        }
        MouseArea { id: rowMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: window.select(account) }
    }
    component GameRankLine: RowLayout {
        property string game: ""
        property string rankText: ""
        property string detailText: ""
        property string iconSource: ""
        property color colorAccent: window.accent
        Layout.fillWidth: true; spacing: 9
        Rectangle { Layout.preferredWidth: 5; Layout.preferredHeight: 26; radius: 2; color: colorAccent }
        Image { visible: iconSource.length > 0; source: iconSource; sourceSize.width: 30; sourceSize.height: 30; Layout.preferredWidth: 26; Layout.preferredHeight: 26; fillMode: Image.PreserveAspectFit }
        ColumnLayout { Layout.fillWidth: true; spacing: 1; Text { text: game; color: window.textQuiet; font.family: "Segoe UI"; font.pixelSize: 8; font.bold: true; font.letterSpacing: 0.6 } Text { text: rankText; color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 11; font.bold: true } }
        Text { text: detailText; color: window.textSecondary; font.family: "Segoe UI"; font.pixelSize: 10 }
    }
    component RankPanel: Rectangle {
        property string title: ""
        property string rankText: ""
        property string detailText: ""
        property string iconSource: ""
        property color accentColor: window.accent
        Layout.fillWidth: true; Layout.preferredHeight: 105; radius: 10; color: window.panel; border.color: window.line
        RowLayout { anchors.left: parent.left; anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 15; spacing: 10; Image { visible: iconSource.length > 0; source: iconSource; sourceSize.width: 34; sourceSize.height: 34; Layout.preferredWidth: 30; Layout.preferredHeight: 30; fillMode: Image.PreserveAspectFit } ColumnLayout { Layout.fillWidth: true; spacing: 5; Text { text: title; color: window.textQuiet; font.pixelSize: 8; font.bold: true; font.letterSpacing: 0.7 } Text { text: rankText; color: window.textPrimary; font.pixelSize: 16; font.bold: true } Text { text: detailText; color: accentColor; font.pixelSize: 10 } } }
    }
    component MatchRow: Rectangle {
        id: matchRow
        property var match: ({})
        Layout.fillWidth: true; Layout.preferredHeight: 55; implicitHeight: 55; radius: 7; color: window.panel; border.color: window.line
        opacity: 0
        Component.onCompleted: matchReveal.start()
        NumberAnimation { id: matchReveal; target: matchRow; property: "opacity"; from: 0; to: 1; duration: window.motionFast; easing.type: Easing.OutCubic }
        RowLayout { anchors.fill: parent; anchors.leftMargin: 15; anchors.rightMargin: 15; Text { text: window.matchGameLabel(match); color: window.textPrimary; font.pixelSize: 11; Layout.preferredWidth: 145 } Text { text: String(window.value(match, "result", "—")); color: ["win", "victory", "top 4"].indexOf(String(window.value(match, "result", "")).toLowerCase()) >= 0 ? window.good : window.textSecondary; font.pixelSize: 11; font.bold: true; Layout.preferredWidth: 100 } Text { text: String(window.value(match, "mode", window.value(match, "queue", "Ranked"))); color: window.textSecondary; font.pixelSize: 11; Layout.preferredWidth: 130 } Text { text: String(window.value(match, "playedAt", window.value(match, "played", window.value(match, "date", "—")))); color: window.textSecondary; font.pixelSize: 11; Layout.fillWidth: true } }
    }
    component MatchTeam: Rectangle {
        property var team: ({})
        Layout.fillWidth: true; Layout.preferredHeight: 236; radius: 10; color: window.panel; border.color: window.line
        ColumnLayout { anchors.fill: parent; anchors.margins: 14; spacing: 8
            RowLayout { Layout.fillWidth: true; Layout.preferredHeight: 26; Text { text: String(window.value(team, "name", "Team")); color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true } Text { text: String(window.value(team, "score", "—")); color: window.accent; font.family: "Segoe UI"; font.pixelSize: 13; font.bold: true } }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: window.line }
            Repeater { model: window.value(team, "players", []); delegate: Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 31; radius: 6; color: playerMouse.containsMouse ? window.panelHover : "transparent"; RowLayout { anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8; spacing: 8; Rectangle { Layout.preferredWidth: 6; Layout.preferredHeight: 6; radius: 3; color: Boolean(window.value(modelData, "self", false)) ? window.accent : window.textQuiet } Text { text: window.identityLabel(modelData); color: window.textPrimary; font.family: "Segoe UI"; font.pixelSize: 10; Layout.fillWidth: true; elide: Text.ElideRight } Text { text: String(window.value(modelData, "agent", window.value(modelData, "rank", "—"))); color: window.textSecondary; font.family: "Segoe UI"; font.pixelSize: 9; Layout.preferredWidth: 64; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight } Text { text: String(window.value(modelData, "score", "—")); color: window.textSecondary; font.family: "Segoe UI"; font.pixelSize: 9; Layout.preferredWidth: 58; horizontalAlignment: Text.AlignRight } } MouseArea { id: playerMouse; anchors.fill: parent; hoverEnabled: true } } }
            Item { Layout.fillHeight: true }
        }
    }
    component SearchResultRow: Rectangle {
        id: searchResultRow
        property var result: ({})
        Layout.fillWidth: true; Layout.preferredHeight: 72; implicitHeight: 72; radius: 9; color: window.panel; border.color: window.line
        opacity: 0
        scale: 0.99
        Component.onCompleted: searchReveal.start()
        ParallelAnimation {
            id: searchReveal
            NumberAnimation { target: searchResultRow; property: "opacity"; from: 0; to: 1; duration: window.motionFast; easing.type: Easing.OutCubic }
            NumberAnimation { target: searchResultRow; property: "scale"; from: 0.99; to: 1; duration: window.motionFast; easing.type: Easing.OutCubic }
        }
        RowLayout { anchors.fill: parent; anchors.margins: 14; spacing: 12; Rectangle { Layout.preferredWidth: 34; Layout.preferredHeight: 34; radius: 17; color: "#26303E"; Text { anchors.centerIn: parent; text: window.accountName(result).charAt(0).toUpperCase(); color: window.accent; font.pixelSize: 13; font.bold: true } } ColumnLayout { Layout.fillWidth: true; spacing: 1; Text { text: window.accountName(result); color: window.textPrimary; font.pixelSize: 12; font.bold: true } Text { text: String(window.value(result, "currentRank", window.rank(result, searchGame.currentText.toLowerCase()))); color: window.textSecondary; font.pixelSize: 10 } Text { text: "Last game  " + String(window.value(result, "lastGame", "No recent game")); color: window.textQuiet; font.pixelSize: 9 } } Button { text: "History  ›"; font.family: "Segoe UI"; font.pixelSize: 10; palette.buttonText: window.accent; background: Rectangle { radius: 7; color: "transparent"; border.color: window.line } onClicked: window.select(result) } Button { text: Boolean(window.value(result, "followed", false)) ? "Unwatch" : "☆  Watch"; font.family: "Segoe UI"; font.pixelSize: 10; palette.buttonText: Boolean(window.value(result, "followed", false)) ? window.textSecondary : window.accent; background: Rectangle { radius: 7; color: "transparent"; border.color: window.line } onClicked: if (window.bridge && window.bridge.toggleWatchlist) window.bridge.toggleWatchlist(window.accountId(result)) } }
    }
    component FollowedRow: Rectangle {
        id: followedRow
        property var account: ({})
        width: ListView.view.width; implicitHeight: 66; height: implicitHeight; radius: 8; color: window.panel; border.color: window.line
        opacity: 0
        Component.onCompleted: followedReveal.start()
        NumberAnimation { id: followedReveal; target: followedRow; property: "opacity"; from: 0; to: 1; duration: window.motionFast; easing.type: Easing.OutCubic }
        RowLayout { anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; spacing: 15; Rectangle { Layout.preferredWidth: 31; Layout.preferredHeight: 31; radius: 16; color: "#26303E"; Text { anchors.centerIn: parent; text: window.accountName(account).charAt(0).toUpperCase(); color: window.accent; font.pixelSize: 11; font.bold: true } } Text { text: window.accountName(account); color: window.textPrimary; font.pixelSize: 11; font.bold: true; Layout.fillWidth: true } Text { text: window.dateLabel(account); color: window.textSecondary; font.pixelSize: 10; Layout.preferredWidth: 160 } Text { text: window.followedCurrentRank(account) + "  /  " + window.followedPeakRank(account); color: window.textSecondary; font.pixelSize: 10; Layout.preferredWidth: 190 } Text { text: "›"; color: window.accent; font.pixelSize: 17 } }
        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: window.select(account) }
    }
    component MenuAction: Item {
        property string label: ""
        property string glyph: ""
        signal triggered()
        width: parent ? parent.width : 200; height: 38
        Rectangle { anchors.fill: parent; radius: 6; color: menuMouse.containsMouse ? window.panelHover : "transparent" }
        RowLayout { anchors.fill: parent; anchors.leftMargin: 9; anchors.rightMargin: 9; spacing: 9; Text { text: glyph; color: window.accent; font.pixelSize: 15; Layout.preferredWidth: 18 } Text { text: label; color: window.textPrimary; font.pixelSize: 11; Layout.fillWidth: true } }
        MouseArea { id: menuMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: parent.triggered() }
    }
    component SettingRow: Rectangle {
        property string title: ""
        property string description: ""
        default property alias control: controlSlot.data
        Layout.fillWidth: true; Layout.preferredHeight: 70; radius: 9; color: window.panel; border.color: window.line
        RowLayout { anchors.fill: parent; anchors.margins: 16; spacing: 15; ColumnLayout { Layout.fillWidth: true; spacing: 3; Text { text: title; color: window.textPrimary; font.pixelSize: 12; font.bold: true } Text { text: description; color: window.textSecondary; font.pixelSize: 10; wrapMode: Text.WordWrap; Layout.fillWidth: true } } Item { id: controlSlot; Layout.preferredWidth: 140; Layout.alignment: Qt.AlignVCenter } }
    }
    component DetailLine: RowLayout { property string label: ""; property string detail: ""; Layout.fillWidth: true; Text { text: label; color: window.textQuiet; font.pixelSize: 9; font.bold: true; Layout.preferredWidth: 150 } Text { text: detail; color: window.textPrimary; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight } }
    component MatchStat: Rectangle { property string label: ""; property string valueText: ""; Layout.fillWidth: true; Layout.preferredHeight: 64; radius: 8; color: window.panel; border.color: window.line; ColumnLayout { anchors.fill: parent; anchors.margins: 13; spacing: 5; Text { text: label; color: window.textQuiet; font.pixelSize: 8; font.bold: true } Text { text: valueText; color: window.textPrimary; font.pixelSize: 11; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true } } }
    component Toast: Rectangle { property string text: ""; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 24; z: 50; width: toastLabel.implicitWidth + 34; height: 38; radius: 19; color: "#E9EDF3"; Behavior on opacity { NumberAnimation { duration: window.motionFast; easing.type: Easing.OutCubic } } Text { id: toastLabel; anchors.centerIn: parent; text: parent.text; color: window.ink; font.family: "Segoe UI"; font.pixelSize: 11 } }
}
