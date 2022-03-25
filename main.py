import os
import random
import shelve
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for
from flask_wtf import FlaskForm
from wtforms import SubmitField, StringField, DateTimeField, DateField
from flask_uploads import UploadSet, configure_uploads, IMAGES, patch_request_class
from wtforms.validators import Length, DataRequired
from flask_wtf.file import FileField, FileRequired, FileAllowed

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'you-will-never-guess'
app.config['UPLOADED_PHOTOS_DEST'] = os.path.join(basedir, 'static')

photos = UploadSet('photos', IMAGES)
configure_uploads(app, photos)
patch_request_class(app)  # set maximum file size, default is 16MB


class Meetings:
    def __init__(self, meetingStart, meetingEnd, thumbnail):
        self.startDate = meetingStart   # datetime object
        self.EndDate = meetingEnd   # datetime object
        self.thumbnail = thumbnail  # image


class MM:  # short for Meeting Management
    adminAccess = False  # boolean variable to ensure that only certified people can create a meeting
    admin_pinCode = '00000'  # pin code used for logging in when creating new meeting
    admin_reservationCode = '00000'  # reservation code used for logging in when creating new meeting
    meetings = []  # list to store all Meetings class instances
    meetingsStartIndex = int(0)  # variable to filter out the meetings which start in the past
    # (since the meeting list is sorted the events from the past take place from index 0 to index meetingsStartIndex)
    clients = dict({})  # dictionary that stores clients data. clients[(pin, reservationCode)] = [reserved meetings IDs]
    reservationCodes = [admin_reservationCode]  # reservation codes generated so far
    codeLength = int(5)  # variable for setting length of generated codes
    file = shelve.open('dataFile', writeback=True)  # file that stores all the data

    @staticmethod
    def getReservationCode():
        for i in range(0, 10000):
            possibleCode = str(i).rjust(MM.codeLength, '0')
            if possibleCode not in MM.reservationCodes:
                MM.reservationCodes.append(possibleCode)
                return possibleCode

    @staticmethod
    def getPinCode():
        return str(random.randint(0, 99999)).rjust(MM.codeLength, '0')

    @staticmethod
    def cancelReservation(pinCode, reservationCode, meetings_for_cancelling):
        cancellingNotSuccessful = []
        for meeting in meetings_for_cancelling:
            if (MM.meetings[meeting].startDate - datetime.today()) < timedelta(days=2):
                cancellingNotSuccessful.append(meeting)
            elif meeting in MM.clients[(pinCode, reservationCode)]:
                MM.clients[(pinCode, reservationCode)].remove(meeting)

        if cancellingNotSuccessful != []:
            message = "You cannot cancel reservation for event less than 2 days before their starting date." \
                      + str(len(cancellingNotSuccessful)) + " meeting reservations could not be canceled."
            return render_template("error.html", message=message)
        else:
            if MM.clients[(pinCode, reservationCode)] == []:
                del MM.clients[(pinCode, reservationCode)]

            MM.saveData()
            return render_template("process_successful.html",
                                   message="Cancelling reservation for chosen events went successfully.")

    @staticmethod
    def addClient(meetingsReserved):
        pinCode = MM.getPinCode()
        reservationCode = MM.getReservationCode()
        MM.clients[(pinCode, reservationCode)] = meetingsReserved
        MM.saveData()
        return pinCode, reservationCode

    @staticmethod
    def addMeeting(startDate,  endDate, filename):
        if endDate > startDate >= datetime.today():
            MM.meetings.append(Meetings(startDate, endDate, filename))
            MM.meetings.sort(key=lambda inst: inst.startDate)
            MM.saveData()
            return render_template("process_successful.html", message="New meeting has been created.")
        else:
            return render_template("error.html",
                                   message="You cannot create event that finishes before it starts"
                                           " or is taking place in the past.")

    @staticmethod
    def checkDates():
        while MM.meetings[MM.meetingsStartIndex].startDate < datetime.today():
            MM.meetingsStartIndex += 1

    @staticmethod
    def loadData():
        MM.meetings = MM.file['meetings']
        MM.meetingsStartIndex = MM.file['meetingsStartIndex']
        MM.clients = MM.file['clients']
        MM.reservationCodes = MM.file['reservationCodes']

    @staticmethod
    def saveData():

        """# I left this in case the database file would get corrupted. If so, you can easily recreate it
        # by uncommenting this part and the one in main(). Here remember to comment out the MM.file.sync()
        MM.file['meetings'] = MM.meetings
        MM.file['meetingsStartIndex'] = MM.meetingsStartIndex
        MM.file['clients'] = MM.clients
        MM.file['reservationCodes'] = MM.reservationCodes"""
        MM.file.sync()
        MM.file.close()


class LogInForm(FlaskForm):
    reservationCode = StringField("Reservation code:",
                                  validators=[Length(min=MM.codeLength, max=MM.codeLength), DataRequired()],
                                  description=str(MM.codeLength) + " digit code generated for meeting identification")
    pinCode = StringField("Pin code:",
                          validators=[Length(min=MM.codeLength, max=MM.codeLength), DataRequired()],
                          description=str(MM.codeLength) + " digit pin code generated for meetings management")
    submitButton = SubmitField("Log in")


class MeetingCreationForm(FlaskForm):
    meetingStart = DateField("Start date", format="%Y-%m-%-d", validators=[DataRequired()])

    meetingStart_hour = DateTimeField("Start hour", format="%-H:%M",
                                      description="Time in 24h format with \':\' as a delimiter. Example: 14:30",
                                      validators=[DataRequired()])

    meetingEnd = DateField("End date", format="%Y-%m-%-d", validators=[DataRequired()])

    meetingEnd_hour = DateTimeField("End hour", format="%-H:%M",
                                    description="Time in 24h format with \':\' as a delimiter. Example: 14:30",
                                    validators=[DataRequired()])

    thumbnail = FileField(validators=[FileAllowed(photos, 'Image only!'), FileRequired('File was empty!')])

    submitButton = SubmitField("Create meeting")


@app.route('/', methods=['GET', 'POST'])
def home():
    MM.checkDates()
    MM.adminAccess = False
    return render_template("home.html")


@app.route('/logIn', methods=['GET', 'POST'])
def logIn():
    form = LogInForm()
    if form.validate_on_submit():
        reservationCode = form.reservationCode.data
        pinCode = form.pinCode.data
        if reservationCode == MM.admin_reservationCode and pinCode == MM.admin_pinCode:
            MM.adminAccess = True
            return redirect(url_for('meetingCreation'))
        elif (pinCode, reservationCode) in MM.clients:
            return redirect(url_for('meetingCancelling', pinCode=pinCode, reservationCode=reservationCode))
        else:
            return render_template("error.html", message="We were unable to log you in. Invalid credentials provided.")

    return render_template("log_in.html", form=form)


@app.route('/meetingCancelling/<string:pinCode>/<string:reservationCode>', methods=['GET', 'POST'])
def meetingCancelling(pinCode, reservationCode):
    """
    1)  reservedMeetings list stores COPY of each meeting
    the client has reservation for that has not taken place yet.

    2) validIds list stores all IDs of meetings that the client has reservation for
    and that haven't happened yet

    3) MM.clients[(pinCode, reservationCode)] stores all meeting that the client has or had reservation for
    with no regard to their starting date

    4) MM.meetingsStartIndex is a variable that lets us filter out all the events that taken place already
    since the MM.meetings are sorted by date of start of the event

    5) selectedMeetingsIds list has ids of all events the user has selected, adjusted for their order of display,
    which means that ids in that list correspond to the ids in the MM.meetings list
    """

    reservedMeetings = []
    validIds = []
    for reservedMeetingId in MM.clients[(pinCode, reservationCode)]:
        if reservedMeetingId >= MM.meetingsStartIndex:
            validIds.append(reservedMeetingId)
            reservedMeetings.append(MM.meetings[reservedMeetingId])

    if request.method == "POST":
        selectedDisplayedMeetingsIds = list(map(int, request.form.getlist('meetingsCheckbox')))
        selectedMeetingsIds = []
        for meetingId in selectedDisplayedMeetingsIds:
            selectedMeetingsIds.append(validIds[meetingId])

        return MM.cancelReservation(pinCode, reservationCode, selectedMeetingsIds)

    return render_template("meetings_display.html", data=reservedMeetings,
                           startIndex=0, endIndex=len(reservedMeetings),
                           title="Reservation cancelling", checkboxMsg="Cancel reservation for this event",
                           message="which reservation you want to cancel")


@app.route('/meetingReservation', methods=['GET', 'POST'])
def meetingReservation():
    if request.method == "POST":
        selectedMeetingsIds = list(map(int, request.form.getlist('meetingsCheckbox')))

        pinCode, reservationCode = MM.addClient(selectedMeetingsIds)
        message = "Your pin code is:\t" + str(pinCode) + "\nAnd your reservation code is:\t" + str(reservationCode)
        return render_template("process_successful.html", message=message)

    return render_template("meetings_display.html", data=MM.meetings,
                           startIndex=MM.meetingsStartIndex, endIndex=len(MM.meetings),
                           title="Meeting reservation", checkboxMsg="Enroll for this event",
                           message="in which participation you are interested")


@app.route('/meetingCreation', methods=['GET', 'POST'])
def meetingCreation():
    if not MM.adminAccess:
        return redirect(url_for('logIn'))

    form = MeetingCreationForm()
    if form.validate_on_submit():
        filename = photos.save(form.thumbnail.data)
        completeStartDate = datetime.combine(form.meetingStart.data, form.meetingStart_hour.data.time())
        completeEndDate = datetime.combine(form.meetingEnd.data, form.meetingEnd_hour.data.time())
        return MM.addMeeting(completeStartDate, completeEndDate, filename)

    return render_template("meeting_creation.html", form=form)


if __name__ == '__main__':

    """# I left this in case the database file would get corrupted. If so, you can easily recreate it
    # by uncommenting this part and the one in MM.saveData()
    MM.meetings.append(
        Meetings(datetime(2022, 3, 8, 12, 30, 0, ), datetime(2022, 3, 11, 14, 30, 0, ), "a.jpg"))
    MM.meetings.append(
        Meetings(datetime(2022, 12, 11, 12, 30, 0, ), datetime(2022, 12, 11, 14, 30, 0, ), "b.jpg"))
    MM.meetings.append(
        Meetings(datetime(2022, 12, 11, 14, 30, 0, ), datetime(2022, 12, 11, 16, 30, 0, ), "c.jpg"))
    MM.meetings.append(
        Meetings(datetime(2022, 12, 13, 14, 30, 0, ), datetime(2022, 12, 13, 16, 30, 0, ), "d.jpg"))
    MM.meetings.append(
        Meetings(datetime(2023, 1, 14, 14, 30, 0, ), datetime(2023, 1, 14, 16, 30, 0, ), "e.jpg"))

    MM.meetings.sort(key=lambda inst: inst.startDate)
    MM.saveData()"""
    MM.loadData()

    app.run(debug=True)
