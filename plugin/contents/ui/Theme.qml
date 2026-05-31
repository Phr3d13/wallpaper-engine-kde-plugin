pragma Singleton
import QtQuick 2.0
import org.kde.kirigami 2.4 as Kirigami

Item {
    id: root_item

    property var textColor:                Kirigami.Theme.textColor
    property var highlightColor:           Kirigami.Theme.highlightColor
    property var highlightedTextColor:     Kirigami.Theme.highlightedTextColor
    property var backgroundColor:          Kirigami.Theme.backgroundColor
    property var activeBackgroundColor:    Kirigami.Theme.activeBackgroundColor
    property var alternateBackgroundColor: Kirigami.Theme.alternateBackgroundColor
    property var linkColor:                Kirigami.Theme.linkColor
    property var visitedLinkColor:         Kirigami.Theme.visitedLinkColor
    property var positiveTextColor:        Kirigami.Theme.positiveTextColor
    property var positiveBackgroundColor:  Kirigami.Theme.positiveBackgroundColor
    property var neutralTextColor:         Kirigami.Theme.neutralTextColor
    property var negativeTextColor:        Kirigami.Theme.negativeTextColor
    property var disabledTextColor:        Kirigami.Theme.disabledTextColor

    readonly property alias view: theme_view

    Item {
        id: theme_view
        Kirigami.Theme.colorSet: Kirigami.Theme.View
        Kirigami.Theme.inherit: false

        property var textColor:                Kirigami.Theme.textColor
        property var highlightColor:           Kirigami.Theme.highlightColor
        property var highlightedTextColor:     Kirigami.Theme.highlightedTextColor
        property var backgroundColor:          Kirigami.Theme.backgroundColor
        property var activeBackgroundColor:    Kirigami.Theme.activeBackgroundColor
        property var alternateBackgroundColor: Kirigami.Theme.alternateBackgroundColor
        property var linkColor:                Kirigami.Theme.linkColor
        property var visitedLinkColor:         Kirigami.Theme.visitedLinkColor
        property var positiveTextColor:        Kirigami.Theme.positiveTextColor
        property var positiveBackgroundColor:  Kirigami.Theme.positiveBackgroundColor
        property var neutralTextColor:         Kirigami.Theme.neutralTextColor
        property var negativeTextColor:        Kirigami.Theme.negativeTextColor
        property var disabledTextColor:        Kirigami.Theme.disabledTextColor
    }
}
