'''
    This script compute the trajectory of a multiple players and reproduce the trajectory on the basketball diagram.
    Moreover, it evalueates the length of the trajectory, the acceleration and the average speed of the player in a given timestep.
'''
import cv2 as cv
import numpy as np
import yaml
import scipy as sp
from scipy import signal
from sklearn.metrics import mean_squared_error
import matplotlib.pyplot as plt
import time
import colorutils
from kalman_filter import KalmanFilter


def createTracker(trackerType):
    trackerTypes = ['BOOSTING', 'MIL', 'KCF', 'TLD', 'MEDIANFLOW', 'GOTURN', 'MOSSE', 'CSRT']
    if trackerType == trackerTypes[0]:
        tracker = cv.legacy.TrackerBoosting_create()
    elif trackerType == trackerTypes[1]:
        tracker = cv.legacy.TrackerMIL_create()
    elif trackerType == trackerTypes[2]:
        tracker = cv.legacy.TrackerKCF_create()
    elif trackerType == trackerTypes[3]:
        tracker = cv.legacy.TrackerTLD_create()
    elif trackerType == trackerTypes[4]:
        tracker = cv.legacy.TrackerMedianFlow_create()
    elif trackerType == trackerTypes[5]:
        tracker = cv.legacy.TrackerGOTURN_create()
    elif trackerType == trackerTypes[6]:
        tracker = cv.legacy.TrackerMOSSE_create()
    elif trackerType == trackerTypes[7]:
        tracker = cv.legacy.TrackerCSRT_create()
    else:
        tracker = None
        print(f'Incorrect tracker name, available trackers are: {trackerTypes}')
    return tracker


def returnIntersection(hist_1, hist_2):
    minima = np.minimum(hist_1, hist_2)
    intersection = np.true_divide(np.sum(minima), np.sum(hist_2))
    return intersection


SHOW_MASKS = False
SHOW_HOMOGRAPHY = False
MANUAL_BOX_SELECTION = True

# Read congigurations
with open('config.yaml') as f:
    loadeddict = yaml.full_load(f)
    TRACKER = loadeddict.get('tracker')
    TAU = loadeddict.get('tau')
    RESIZE_FACTOR = loadeddict.get('resize_factor')

# Read homography matrix
with open('configs/homography_19points.yaml') as f:
    dict_homo = yaml.full_load(f)
    h = np.array(dict_homo.get('homography'))

img = cv.imread(loadeddict.get('input_image_homography'))

# Set output video
fourcc = cv.VideoWriter_fourcc(*'DIVX')

cap = cv.VideoCapture(loadeddict.get('input_video'))
fps = cap.get(cv.CAP_PROP_FPS)

if not cap.isOpened():
    exit("Input video not opened correctly")

ok, frame = cap.read()
smallFrame = cv.resize(frame, (0, 0), fx=RESIZE_FACTOR, fy=RESIZE_FACTOR)
kalman_filters, kalman_filtersp1, kalman_filtersp2 = [], [], []
color_names_used = set()
bboxes = []
colors = []
histo = []

out = cv.VideoWriter(loadeddict.get('out_players'), fourcc, 25.0, smallFrame.shape[1::-1])
out_mask = cv.VideoWriter(loadeddict.get('out_players_mask'), fourcc, 25.0, smallFrame.shape[1::-1])
points = cv.VideoWriter(loadeddict.get('out_homography'), fourcc, 25.0, img.shape[1::-1])

if MANUAL_BOX_SELECTION:
    while True:
        # draw bounding boxes over objects
        # selectROI's default behaviour is to draw box starting from the center
        # when fromCenter is set to false, you can draw box starting from top left corner
        bbox = cv.selectROI('ROI', smallFrame, False)
        if bbox == (0, 0, 0, 0):
            break  #no box selected
        crop_img = smallFrame[int(bbox[1]):int(bbox[1] + bbox[3]), int(bbox[0]):int(bbox[0] + bbox[2])]
        hist_1, _ = np.histogram(crop_img, bins=256, range=[0, 255])
        histo.append(hist_1)
        bboxes.append(bbox)
        colors.append(colorutils.pickNewColor(color_names_used))
        print('Press q to quit selecting boxes and start tracking, or any other key to select next object')
        if (cv.waitKey(0) & 0xFF == ord('q')):  # q is pressed
            break
else:
    for bbox in  [(722, 264, 21, 47) , (262, 270, 16, 33)]: # (205, 280, 22, 42), (543, 236, 17, 38), (262, 270, 16, 33), (722, 264, 21, 47)
        crop_img = smallFrame[int(bbox[1]):int(bbox[1] + bbox[3]), int(bbox[0]):int(bbox[0] + bbox[2])]
        hist_1, _ = np.histogram(crop_img, bins=256, range=[0, 255])
        histo.append(hist_1)
        bboxes.append(bbox)
        colors.append(colorutils.pickNewColor(color_names_used)) 


cv.destroyWindow('ROI')
print('Selected bounding boxes: {}'.format(bboxes))
multiTracker = cv.legacy.MultiTracker_create()
# List for saving points of tracking in the basketball diagram (homography)
x_sequence_image, y_sequence_image = [], []
x_sequences, y_sequences = [], []
#ok, frame = cap.read()
#smallFrame = cv.resize(frame, (0, 0), fx=0.35, fy=0.35)
for i, bbox in enumerate(bboxes):
    multiTracker.add(createTracker(TRACKER), smallFrame, bbox)
    x_sequences.append([])
    y_sequences.append([])
    kalman_filters.append(KalmanFilter())
    kalman_filtersp1.append(KalmanFilter())
    kalman_filtersp2.append(KalmanFilter())

    tracking_point = (int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3]))
    cv.circle(smallFrame, (tracking_point[0], tracking_point[1]), 4, (255, 200, 0), -1)
    cv.rectangle(smallFrame, (bbox[0], bbox[1]), (bbox[0] + bbox[2], bbox[1] + bbox[3]), (255, 0, 0), 2)
    # Compute the point in the homographed space: destination point(image)=homography matrix*source point(video)
    vector = np.dot(h, np.transpose([tracking_point[0], tracking_point[1], 1]))
    # Evaluation of the vector
    tracking_point_img = (vector[0], vector[1])
    w = vector[2]
    tracking_point_new = (int(tracking_point_img[0] / w), int(tracking_point_img[1] / w))
    x_sequences[i].append(tracking_point_new[0])
    y_sequences[i].append(tracking_point_new[1])
    cv.circle(img, (tracking_point_new[0], tracking_point_new[1]), 4, colors[i], -1)

# Save and visualize the chosen bounding box and its point used for homography
cv.imwrite(loadeddict.get('out_bboxes'), smallFrame)
cv.putText(smallFrame, 'Selected Bounding Boxes. PRESS SPACE TO CONTINUE...', (20, 20), cv.FONT_HERSHEY_SIMPLEX, 0.75, (50, 170, 50), 2)
cv.imshow('Tracking', smallFrame)
cv.waitKey(0)

index = 1
start = time.time()
while (1):
    if index > 50:
        ok, frame = cap.read()
    if ok:
        smallFrame = cv.resize(frame, (0, 0), fx=RESIZE_FACTOR, fy=RESIZE_FACTOR)
        maskedFrame = np.zeros(smallFrame.shape)
        cv.putText(smallFrame, TRACKER + ' Tracker', (100, 20), cv.FONT_HERSHEY_SIMPLEX, 0.75, (50, 170, 50), 2)
        ok, boxes = multiTracker.update(smallFrame)
        # Update position of the bounding box
        for i, newbox in enumerate(boxes):
            p1 = (int(newbox[0]), int(newbox[1]))
            p2 = (int(newbox[0] + newbox[2]), int(newbox[1] + newbox[3]))
            # Computation of the new position of the tracking point
            tracking_point = (int(newbox[0] + newbox[2] / 2), int(newbox[1] + newbox[3]))
            predictedCoords = kalman_filters[i].estimate(tracking_point[0], tracking_point[1])
            p1 = kalman_filtersp1[i].estimate(p1[0], p1[1])
            p2 = kalman_filtersp2[i].estimate(p2[0], p2[1])
            # Compute the point in the homographed space: destination point(image)=homography matrix*source point(video)
            vector = np.dot(h, np.transpose([predictedCoords[0][0], predictedCoords[1][0], 1]))
            if index <= 50:
                index += 1
            else:
                tracking_point_img = (vector[0], vector[1])
                w = vector[2]
                tracking_point_new = (int(tracking_point_img[0] / w), int(tracking_point_img[1] / w))
                # Add new position to list of points for the homographed space
                x_sequences[i].append(tracking_point_new[0])
                y_sequences[i].append(tracking_point_new[1])
                # computation of the predicted bounding box
                punto1 = (int(p1[0]), int(p1[1]))
                punto2 = (int(p2[0]), int(p2[1]))
                bbox_new = (punto1[0], punto1[1], punto2[0] - punto1[0], punto2[1] - punto1[1])

                crop_img = smallFrame[int(bbox_new[1]):int(bbox_new[1] + bbox_new[3]), int(bbox_new[0]):int(bbox_new[0] + bbox_new[2])]
                hist_2, _ = np.histogram(crop_img, bins=256, range=[0, 255])
                intersection = returnIntersection(histo[i], hist_2)
                if intersection < TAU:
                    print('RE-INITIALIZE TRACKER CSRT n° %d' % i)
                    colors[i] = colorutils.pickNewColor(color_names_used)
                    multiTracker = cv.legacy.MultiTracker_create()
                    for n, nb in enumerate(boxes):
                        boxi = (int(nb[0]), int(nb[1]), int(nb[2]), int(nb[3]))
                        if n == i:
                            multiTracker.add(createTracker(TRACKER), smallFrame, bbox_new)
                        else:
                            multiTracker.add(createTracker(TRACKER), smallFrame, boxi)

                    histo[i] = hist_2

                cv.putText(smallFrame, '{:.2f}'.format(intersection), (punto1[0], punto1[1]-7), cv.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                cv.rectangle(smallFrame, punto1, punto2, colors[i], 2, 1)
                cv.circle(smallFrame, (int(predictedCoords[0][0]), int(predictedCoords[1][0])), 4, colors[i], -1)
                cv.circle(img, (tracking_point_new[0], tracking_point_new[1]), 4, colors[i], -1)
                points.write(img)  # Save video for position tracking on the basketball diagram
                # Compute masked frame
                maskedFrame[int(bbox_new[1]):int(bbox_new[1] + bbox_new[3]), int(bbox_new[0]):int(bbox_new[0] + bbox_new[2])] = [255, 255, 255]
                # Show results
                cv.imshow('Tracking', smallFrame)
                if SHOW_MASKS:
                    cv.imshow('Tracking-Masks', maskedFrame)
                if SHOW_HOMOGRAPHY:
                    cv.imshow('Tracking-Homography', img)

        if index > 50:
            out.write(smallFrame)  # Save video frame by frame
            out_mask.write(maskedFrame)  # Save masked video

        if cv.waitKey(1) & 0xFF == ord('q'):
            break

    else:  
        cv.putText(smallFrame, 'Tracking failure detected', (100, 80), cv.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 3)
        break

cv.waitKey(0)
cv.destroyAllWindows()
end = time.time()
print(f'\nTotal time consumed for tracking: {(end - start):.2f}s')

# Post-processing
# 1) Apply a median filter to the two sequence of x, y coordinates in order to achieve a smoother trajectory
x_sequence_image = sp.signal.medfilt(x_sequence_image, 25)  # Window width of the filter MUST be ODD
y_sequence_image = sp.signal.medfilt(y_sequence_image, 25)
position_x = []
position_y = []
for i, bbox in enumerate(bboxes):
    x_sequences[i] = sp.signal.medfilt(x_sequences[i], 25)
    y_sequences[i] = sp.signal.medfilt(y_sequences[i], 25)
    # Draw the trajectory on the basketball diagram
    pts = np.column_stack((x_sequences[i], y_sequences[i]))
    pts = np.array(pts, np.int32)
    pts = pts.reshape((-1, 1, 2))
    cv.polylines(img, [pts], False, colors[i], 2)
    position_x.append([])
    position_y.append([])

# Show the result
if SHOW_HOMOGRAPHY:
    cv.imshow('Smoothing', img)
    cv.waitKey(0)
    cv.destroyWindow('Smoothing')

# Evaluation of the shift, acceleration and the average speed of the players in real world coordinates
# Step 1: Compute the position of the smoothed vector of position in real world coordinates
# Step 2: Evaluate the length of the trajectory using an Euclidian distance between 2 successive points and sum them together
#         and compute the acceleration values
# Step 3: Compute the velocity and the total length of the trajectory

# Step 1
flag = 0
index = 0
for bbox in bboxes:
    x_sequence_image = x_sequences[index]
    y_sequence_image = y_sequences[index]
    for i in range(0, len(x_sequence_image) - 1):
        # x coordinate
        length = x_sequence_image[i] - 38
        proportion = length / 1008.0
        position_x[index].append(28 * proportion)
        # y coordinate
        length = y_sequence_image[i] - 28
        proportion = length / 545.0
        position_y[index].append(15 * proportion)
    index += 1
# Step 2
shift = 0
index = 0
px, py = [], []
f = open(loadeddict.get('out_players_data'), 'w+')
f.write('TIME CONSUMED FOR TRACKING: %f\r\n' % (end - start))
for bbox in bboxes:
    px = position_x[index]
    py = position_y[index]
    shift = 0
    rgb = colors[index]
    actual_name, closest_name = colorutils.getColorName(rgb)
    f.write('\n\n')
    f.write('TRACKER COLOR %s\r\n' % closest_name)
    f.write('ACCELERATION:\r\n')
    iter_frame = 1
    shift_prec, average_acceleration1 = None, None
    for i in range(0, len(px) - 1):
        # compute here the accelleration for space sample
        shift = shift + np.sqrt((px[i + 1] - px[i]) ** 2 + (py[i + 1] - py[i]) ** 2)  # steve updated from math.sqrt to np.sqrt
        if i == 50*iter_frame:
            if iter_frame == 1:
                shift_prec = shift
                speed1 = shift_prec / 2
                average_acceleration1 = speed1 / 2
                f.write('Detection done in the first 2 seconds\r\n')
                f.write('route space:%f, time step 2 sec\r\n' % shift_prec)
                f.write('acceleration: %f\r\n' % average_acceleration1)
            else:
                t1 = (((2 * fps) * iter_frame) - (2 * fps)) / fps
                t2 = ((2 * fps) * iter_frame) / fps
                speed2 = (shift - shift_prec) / 2
                average_acceleration2 = speed2 / 2 - average_acceleration1
                average_acceleration1 = average_acceleration2
                f.write('Detection done in the time sample %d - %d sec\r\n' % (t2, t1))
                f.write('route space:%f, time step 2 sec\r\n' % (shift - shift_prec))
                f.write('acceleration: %f\r\n' % average_acceleration2)
                shift_prec = shift

            iter_frame += 1
            f.write('\n')
# Step 3
    # Print of the results
    # Evaluation of the average speed: speed=space/time
    average_speed = shift / (len(px)/fps)
    f.write(f'trajectory length {shift:.2f}[m]\r\n\n')
    f.write(f'average speed {average_speed:.2f}[m/s]\r\n\n')
    cv.imwrite(loadeddict.get('out_tracking_results'), img)
    cv.imshow('Result', img)
    index += 1
cap.release()
cv.destroyAllWindows()
f.close()
