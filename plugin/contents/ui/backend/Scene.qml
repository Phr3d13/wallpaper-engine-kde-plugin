import QtQuick 2.5
import com.github.catsout.wallpaperEngineKde 1.2
import ".."

Item{
    id: sceneItem
    anchors.fill: parent
    property alias source: player.source
    property string assets: "assets"
    property var getAudio
    // Passed from main.qml so we can read saved per-wallpaper config from disk.
    property var readWallpaperConfig
    property int displayMode: background.displayMode
    property var volumeFade: Common.createVolumeFade(
        sceneItem, 
        Qt.binding(function() { return background.mute ? 0 : background.volume; }),
        (volume) => { player.volume = volume / 100.0; }
    )

    // Apply (or re-apply after save) saved user property overrides.
    function applyUserProperties() {
        if (!readWallpaperConfig) return;
        readWallpaperConfig(background.workshopid).then(function(saved) {
            player.setUserProperties(saved || {});
        });
    }

    onDisplayModeChanged: {
        if(displayMode == Common.DisplayMode.Scale)
            player.fillMode = SceneViewer.STRETCH;
        else if(displayMode == Common.DisplayMode.Aspect)
            player.fillMode = SceneViewer.ASPECTFIT;
        else if(displayMode == Common.DisplayMode.Crop)
            player.fillMode = SceneViewer.ASPECTCROP;
    }

    // Re-apply user properties whenever the saved config changes
    // (toggled by WallpaperPage.save_changes after writing to disk).
    Connections {
        target: background
        function onPerOptChangedChanged() {
            sceneItem.applyUserProperties();
        }
    }

    SceneViewer {
        id: player
        anchors.fill: parent
        fps: background.fps
        muted: background.mute
        speed: background.speed
        assets: sceneItem.assets
        Component.onCompleted: {
            player.setAcceptMouse(true);
            player.setAcceptHover(true);
        }

        Connections {
            target: player
            function onFirstFrame() {
                background.sig_backendFirstFrame('scene');
            }
        }
    }

    Timer {
        id: audioTimer
        interval: 33
        running: sceneItem.getAudio !== undefined
        repeat: true
        onTriggered: {
            sceneItem.getAudio().then(function(data) {
                if (data && data.length >= 128) {
                    player.setAudioData(data);
                } else {
                    console.log("[Scene audio] data invalid:", data ? data.length : "null");
                }
            });
        }
    }

    Component.onCompleted: {
        background.nowBackend = 'scene';
        sceneItem.displayModeChanged();
        console.log("[Scene audio] getAudio defined:", sceneItem.getAudio !== undefined);
        // Load saved user properties so they are applied on initial scene parse.
        sceneItem.applyUserProperties();
    }
    function play() {
        volumeFade.start();
        player.play();
    }
    function pause() {
        volumeFade.stop();
        player.pause();
    }
    
    function getMouseTarget() {
        return Qt.binding(function() { return player; })
    }
}
