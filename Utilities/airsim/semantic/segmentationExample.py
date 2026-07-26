import numpy as np
import sys
import airsim
import math
import json

from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import *

import argparse

class MainView(QMainWindow):
    def __init__(self, args):
        super(MainView, self).__init__()
        self.args = args

        self.actionTime = 0.2
        self.speed = 2.5
        self.keyboardPresses = [False, False, False, False, False, False, False, False]

        self.imageMessage = [airsim.ImageRequest("front_left_custom", airsim.ImageType.Scene, False, False),
                             airsim.ImageRequest("front_left_custom", airsim.ImageType.Segmentation, False, False)]

        ###### Setup GUI ######
        self.setContentsMargins(0, 10, 0, 0)
        colourPalette = self.palette()
        colourPalette.setColor(self.backgroundRole(), QtGui.QColor(43, 43, 43))
        self.setPalette(colourPalette)

        self.mainGrid = QGridLayout()

        self.speedLbl = QLabel(self)
        self.speedLbl.setStyleSheet("color:rgb(220, 220, 220); font-size: 20px")
        self.speedLbl.setText(f"Speed: {self.speed}")

        self.controlsLbl = QLabel(self)
        self.controlsLbl.setStyleSheet("color:rgb(220, 220, 220); font-size: 20px")
        self.controlsLbl.setText(f"Controls:\n"
                                 f"W: forward\n"
                                 f"S: backward\n"
                                 f"A: left\n"
                                 f"D: right\n"
                                 f"Up: up\n"
                                 f"Down: down\n"
                                 f"E: yaw right\n"
                                 f"Q: yaw left\n"
                                 f"P: increase speed\n"
                                 f"O: decrease speed")

        self.displayImageFrontLbl = QLabel(self)
        self.displayImageSegmentationLbl = QLabel(self)

        self.mainGrid.addWidget(self.speedLbl, 0, 0, 1, 1)
        self.mainGrid.addWidget(self.controlsLbl, 1, 0, 1, 1)

        self.mainGrid.addWidget(self.displayImageFrontLbl, 0, 1, 2, 1)
        self.mainGrid.addWidget(self.displayImageSegmentationLbl, 2, 1, 2, 1)

        self.mainGridWidget = QWidget()
        self.mainGridWidget.setLayout(self.mainGrid)
        self.setCentralWidget(self.mainGridWidget)

        self.actionTimer = QtCore.QTimer()
        self.actionTimer.timeout.connect(self.getAction)
        self.actionTimer.start(int(self.actionTime * 1000))

        self.client = airsim.MultirotorClient()
        self.client.confirmConnection()
        self.client.enableApiControl(True, vehicle_name='SimpleFlight')
        success = self.client.armDisarm(True, vehicle_name='SimpleFlight')

        if not args.useDefaultSegmentation:

            # Load the segmentation classes from json file
            with open(args.segmentationFile, "r") as f:
                self.segmentationClasses = json.load(f)
            print("All of the known segmentation classes are:")
            print(self.segmentationClasses)
            print()


            # Get a list of all the objects within the scene
            objectList = self.client.simListSceneObjects()
            print(f"Found a total of {len(objectList)} objects within the scene")
            print(objectList)
            print()

            # Change the segmentation ID of all objects to zero
            success = self.client.simSetSegmentationObjectID("[\w]*", 0, True)

            for key in self.segmentationClasses.keys():
                classID = self.segmentationClasses[key]['classID']
                objectNames = self.segmentationClasses[key]['objectNames']

                for object in objectNames:
                    success = self.client.simSetSegmentationObjectID(f"{object}[\w]*", classID, True)
                    if success:
                        print(f"We found a {key} called {object} and changed it's segmentation ID to {classID}")

            # InstancedFoliageActor is a special case that includes certain types of trees but also other foliage assets like fallen leaves
            # Including it into the tree class would detect more trees but will also give false positives to fallen leaves
            # This is a limitation of how the environment was built

    def getAction(self):

        action = np.zeros(3, dtype=np.float32)
        yaw = 0.0

        if self.keyboardPresses[0]:
            action[0] = 1.0
        if self.keyboardPresses[1]:
            action[0] = -1.0
        if self.keyboardPresses[2]:
            action[1] = -1.0
        if self.keyboardPresses[3]:
            action[1] = 1.0
        if self.keyboardPresses[4]:
            action[2] = 1.0
        if self.keyboardPresses[5]:
            action[2] = -1.0
        if self.keyboardPresses[6]:
            yaw = 1.0
        if self.keyboardPresses[7]:
            yaw = -1.0

        action *= self.speed

        pose = self.client.simGetVehiclePose(vehicle_name='SimpleFlight')
        quaternion = np.array([pose.orientation.w_val, pose.orientation.x_val, pose.orientation.y_val, pose.orientation.z_val], dtype=np.float32)
        currentYaw = math.atan2(2 * (quaternion[0] * quaternion[3] + quaternion[1] * quaternion[2]), 1 - 2 * (quaternion[2] ** 2 + quaternion[3] ** 2))
        rot = np.array([[math.cos(currentYaw), -math.sin(currentYaw)],
                        [math.sin(currentYaw), math.cos(currentYaw)]])
        action[0:2] = np.matmul(rot, action[0:2].reshape([2,1])).reshape(-1)


        self.client.moveByVelocityAsync(float(action[0]), float(action[1]), float(action[2]), self.actionTime * 2.0, yaw_mode=airsim.YawMode(True, yaw * 180 / math.pi), vehicle_name=f"SimpleFlight")


        images = self.client.simGetImages(self.imageMessage, vehicle_name='SimpleFlight')

        forwardRGB = np.frombuffer(images[0].image_data_uint8, dtype=np.uint8)
        forwardRGB = forwardRGB.reshape([images[0].height, images[0].width, 3])
        # QtImage = QtGui.QImage(forwardRGB.data, forwardRGB.shape[1], forwardRGB.shape[0], forwardRGB.shape[1] * 3, QtGui.QImage.Format_BGR888)
        QtImage = QtGui.QImage(forwardRGB.data, forwardRGB.shape[1], forwardRGB.shape[0], forwardRGB.shape[1] * 3, QtGui.QImage.Format_RGB888).rgbSwapped()

        self.displayImageFrontLbl.setPixmap(QtGui.QPixmap(QtImage))

        segmentationImage = np.frombuffer(images[1].image_data_uint8, dtype=np.uint8)
        segmentationImage = segmentationImage.reshape([images[0].height, images[0].width, 3])
        # QtImage = QtGui.QImage(segmentationImage.data, segmentationImage.shape[1], segmentationImage.shape[0], segmentationImage.shape[1] * 3, QtGui.QImage.Format_BGR888)
        QtImage = QtGui.QImage(segmentationImage.data, segmentationImage.shape[1], segmentationImage.shape[0], segmentationImage.shape[1] * 3, QtGui.QImage.Format_RGB888).rgbSwapped()

        self.displayImageSegmentationLbl.setPixmap(QtGui.QPixmap(QtImage))

    def keyPressEvent(self, event):

        if event.key() == QtCore.Qt.Key_W:
            self.keyboardPresses[0] = True

        elif event.key() == QtCore.Qt.Key_S:
            self.keyboardPresses[1] = True

        elif event.key() == QtCore.Qt.Key_A:
            self.keyboardPresses[2] = True

        elif event.key() == QtCore.Qt.Key_D:
            self.keyboardPresses[3] = True

        elif event.key() == QtCore.Qt.Key_Down:
            self.keyboardPresses[4] = True

        elif event.key() == QtCore.Qt.Key_Up:
            self.keyboardPresses[5] = True

        elif event.key() == QtCore.Qt.Key_E:
            self.keyboardPresses[6] = True

        elif event.key() == QtCore.Qt.Key_Q:
            self.keyboardPresses[7] = True

        elif event.key() == QtCore.Qt.Key_P:
            self.speed += 0.1
            self.speedLbl.setText(f"Speed: {self.speed:.1f}")

        elif event.key() == QtCore.Qt.Key_O:
            self.speed -= 0.1
            self.speedLbl.setText(f"Speed: {self.speed:.1f}")

        event.accept()

    def keyReleaseEvent(self, event):

        if event.key() == QtCore.Qt.Key_W:
            self.keyboardPresses[0] = False

        elif event.key() == QtCore.Qt.Key_S:
            self.keyboardPresses[1] = False

        elif event.key() == QtCore.Qt.Key_A:
            self.keyboardPresses[2] = False

        elif event.key() == QtCore.Qt.Key_D:
            self.keyboardPresses[3] = False

        elif event.key() == QtCore.Qt.Key_Down:
            self.keyboardPresses[4] = False

        elif event.key() == QtCore.Qt.Key_Up:
            self.keyboardPresses[5] = False

        elif event.key() == QtCore.Qt.Key_E:
            self.keyboardPresses[6] = False

        elif event.key() == QtCore.Qt.Key_Q:
            self.keyboardPresses[7] = False

        event.accept()

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Script to a demonstrate how to create custom segmentation examples")
    parser.add_argument('--useDefaultSegmentation', type=bool, help='Get AirSim to automatically generate class IDs?', default=False)
    parser.add_argument('--segmentationFile', type=str, help='Path to the segmentation rule file', default="segmentationClasses.json")
    args = parser.parse_args()

    sys._excepthook = sys.excepthook

    def exception_hook(exctype, value, traceback):
        print(exctype, value, traceback)
        sys._excepthook(exctype, value, traceback)
        sys.exit(1)

    sys.excepthook = exception_hook

    # Start interface
    app = QApplication(sys.argv)
    GUI = MainView(args)
    GUI.show()
    sys.exit(app.exec_())
