try:
    import pifacedigitalio
except ImportError:
    print "import failed for pifacedigitalio"
from Tkinter import *
import time
from threading import Thread
#from threading import Event
import threading
import thread
import signal
import os
import Queue
import inspect
import logging


# 1-wire Thermometer
class Thermometer():
    def __init__(self, device_id):
        self.device_id = device_id
        self.lock = threading.Lock()

    def read_temp(self):
        self.lock.acquire()
        try:
            print "read temp"
            tfile = open("/sys/bus/w1/devices/" + self.device_id + "/w1_slave")
            text = tfile.read()
            tfile.close()
            secondline = text.split("\n")[1]
            temperaturedata = secondline.split(" ")[9]
            temperature = float(temperaturedata[2:])/1000
            self.lock.release()
            return temperature
        except IOError:
            self.lock.release()
            return 0

# Heat control states
class ControlState():
    off = 0
    on = 1
    tc = 2
    tc_stopping = 3
    tc_delayed = 4
    tc_delayed_stopping = 5
    pwm = 6
    pwm_stopping = 7
    pwm_delayed = 8
    pwm_delayed_stopping = 9
    disabled = 10
    shutting_down = 11

class Events():
    btn_off = 0
    btn_tc = 1
    btn_pwm = 2
    controller_stopped = 3
    btn_pwm_delay = 4
    btn_tc_delay = 5
    timer_expired = 6
    set_tc = 7
    set_pwm = 8
    set_pwm_delay_time = 9
    set_tc_delay_time = 10
    timer_stopped = 11
    enable = 12
    disable = 13
    shutdown = 14
    heat_on = 15
    heat_off = 16

class InterrupableSleep():
    def __init__(self):
        self._sleep = threading.Event()

    def sleep(self, delay):
        self._sleep.wait(delay)

    def interrupt(self):
        self._sleep.set()

    def clear(self):
        self._sleep.clear()


# Elements
class Elements:
    def __init__(self, pins, heat_cb):
        self.pins = pins
        self.heat_cb = heat_cb
        self.turned_on = 0
        self.int_sleep = threading.Event()
        try:
            self.pifacedigital = pifacedigitalio.PiFaceDigital()
        except NameError:
            print "pifacedigital is not available on this platform"

    def turn_on(self):
        if (self.turned_on == 0):
            try:
                for pin in self.pins:
                    self.pifacedigital.output_pins[pin].turn_on()
                    time.sleep(0.05)
            except AttributeError:
                print "pifacedigital is not available on this platform"
        print "turn heat on"
        self.turned_on = 1
        self.heat_cb(Events.heat_on)

    def turn_off(self):
        if (self.turned_on != 0):
            self.turned_on = 0
            try:
                for pin in self.pins:
                    self.pifacedigital.output_pins[pin].turn_off()
                    time.sleep(0.05)
            except AttributeError:
                print "pifacedigital is not available on this platform"
            print "turning heat off"
        self.heat_cb(Events.heat_off)

    def interruptable_sleep(self, delay):
        self.int_sleep = threading.Event()
        self.int_sleep.wait(delay)

    def interrupt_sleep(self):
        self.int_sleep.set()

# PWM
class PwmElements(Elements):
    def __init__(self, pins, heat_cb):
        Elements.__init__(self, pins, heat_cb)
        self.latch = 0

    def run(self, period, duty_cycle):
        self.int_sleep.clear()
        self.turn_on()
        print "pwm on time = " + str(duty_cycle * period)
        self.interruptable_sleep(duty_cycle * period)

        if (duty_cycle == 1):
            self.latch = 1
        else:
            self.latch = 0

        if (self.latch != 1):
            self.turn_off()
            print "pwm off time = " + str((1 - duty_cycle) * period)
            self.interruptable_sleep((1 - duty_cycle) * period)
            self.turn_off()

# Controller base class
class Controller():
    def __init__(self, stopped_cb, heat_cb, pins):
        self.target = 0
        self.mode = ControlState.off
        self.turned_on = 0
        self.stopped_cb = stopped_cb
        self.heat_cb = heat_cb
        self.actuator = Elements(pins, heat_cb)
        self.control_sleep = InterrupableSleep()
        self.actuator_sleep = InterrupableSleep()
        try:
            self.pifacedigital = pifacedigitalio.PiFaceDigital()
        except NameError:
            print "pifacedigital is not available on this platform"

    def set_target(self, target):
        self.target = target
        print "set target " + str(target)
  
    def start(self):
        print "starting"
        self.mode = ControlState.on

        # Start control thread
        self.control_sleep.clear()
        self.actuator_sleep.clear() 
        self.control_thread = Thread(target = self.control_run)
        self.control_thread.start()

        # Start control thread
        self.actuate_thread = Thread(target = self.actuate_run)
        self.actuate_thread.start()

    def stop(self):
        print "stopping"
        self.mode = ControlState.off
        self.control_sleep.interrupt()
        self.actuator_sleep.interrupt()
        self.cancel_actuator()

    def control_run(self):
        if(1):
            while (self.mode == ControlState.on):
                try:
                    self.control()
                except:
                    raise

    def actuate_run(self):
        if(1):
            while (self.mode == ControlState.on):
                print "actuate"
                try:
                    self.actuate()
                except:
                    raise 
            self.actuator.turn_off()
            self.stopped_cb(Events.controller_stopped)

    def control(self):
        #print "control() not implemented"
        self.control_sleep.sleep(1)

    def actuate(self):
        print "actuate() not implemented"

    def cancel_actuator(self):
        self.actuator.interrupt_sleep()

# Temperature Control
class TempControl(Controller):
    def __init__(self, stopped_cb, heat_cb, device_id, pins):
        Controller.__init__(self, stopped_cb, heat_cb, pins)
        self.temp = 0
        self.thermometer = Thermometer(device_id)
        self.deadband = 0.5
        self.control_decision = 0

    def control(self):
        self.temp = self.thermometer.read_temp()
        print self.temp
        if ((self.temp + self.deadband) < self.target):
            self.control_decision = 1 
        else:
            self.control_decision = 0
        self.control_sleep.sleep(1)

    def actuate(self):
        print "actuate"
        if (self.control_decision == 1):
            self.actuator.turn_on()
        else:
            self.actuator.turn_off()
        self.actuator_sleep.sleep(1)

# PWM Control
class PwmControl(Controller):
    def __init__(self, stopped_cb, heat_cb, pins):
        Controller.__init__(self, stopped_cb, heat_cb, pins)
        self.actuator = PwmElements(pins, heat_cb)
        self.period = 4
        self.latch = 0
        self.duty_cycle = 0

    def set_duty_cycle(self, duty_cycle):
        self.duty_cycle = duty_cycle
        print "set duty_cycle " + str(duty_cycle)

    def actuate(self):
        self.actuator.run(self.period, self.duty_cycle)

# Tempcontrol with pwm
class VariableTempControl(PwmControl):
    def __init__(self, stopped_cb, heat_cb, device_id, pins):
        PwmControl.__init__(self, stopped_cb, heat_cb, pins)
        self.temp = 0
        self.thermometer = Thermometer(device_id)
        self.deadband = 0.5
        self.control_decision = 0
        
    def control(self):
        self.temp = self.thermometer.read_temp()
        print self.temp
        print self.target
        if ((self.temp + self.deadband) < self.target):
            self.control_decision = 1 
        else:
            self.control_decision = 0
        time.sleep(1)

    def actuate(self):
        if (self.control_decision == 1):
            self.actuator.run(self.period, self.duty_cycle)
        else:
            self.actuator.turn_off()
            self.actuator_sleep.sleep(1)

# Timer
class Timer():
    def __init__(self, expire_cb, stopped_cb, timer_update_cb):
        self.i = 1
        self.seconds = 0
        self.expire_cb = expire_cb
        self.stopped_cb = stopped_cb
        self.timer_update_cb = timer_update_cb

    def start(self, seconds):
        print "delay timer starting"
        self.seconds = seconds
        self.t = Thread(target = self.timer)
        self.t.start()

    def stop(self):
        print "stop delay timer"
        self.seconds = 0
        self.stopped_cb(Events.timer_stopped)
 
    def is_running(self):
        try:
            return self.t.is_alive()
        except:
            return 0

    def timer(self):
        while (self.seconds > 0):
            time.sleep(1)
            print self.seconds
            self.seconds -= 1
            self.timer_update_cb(self.seconds)

            # Let the man upstairs know that the timer has expired
            if (self.seconds == 0):
                print "timer expiring"
                self.expire_cb(Events.
                               timer_expired)

        # Expired or stopped
        self.timer_update_cb(0)

class Gui():

    # Button indexes
    BTN_OFF = 0
    BTN_TC = 1
    BTN_PWM = 2
    BTN_TC_LATER = 3
    BTN_PWM_LATER = 4

    # Action indexes
    ACTION_ENABLE = 0
    ACTION_TEXT = 1
    ACTION_SELECT = 2

    def __init__(self, col_offset, name, device_id, event_cb):
        self.name = name
        self.device_id = device_id

        # Init widgets
        self.col_offset = col_offset
        self.init_frame()
        self.init_temp()
        self.init_control_btns()
        self.init_temp_inputs()
        self.init_btn_enable()
        self.init_status()
        self.init_timer_display()

        # Hook up callbacks for gui events
        self.event_cb = event_cb

        # Start temp read thread
        self.run = 1
        self.thermometer_sleep = InterrupableSleep()
        self.thermometer_sleep.clear()
        self.thermometer = Thermometer(self.device_id)
        self.th = Thread(target = self.read_temp)
        self.th.start()

    def close(self):
        self.run = 0
        self.thermometer_sleep.interrupt()

    def init_frame(self):
        self.frm = Frame(root, relief = RIDGE, borderwidth = 5)
        self.frm.grid(row = 0, column = self.col_offset, sticky = "w")
        self.title = Label(self.frm, text = self.name, font = ("Purisa", 50))
        self.title.grid(row = 0, column = 0, columnspan = 2 ,stick = "w")

    def init_btn_enable(self):
        self.enable = IntVar()
        self.enable.set(0)
        self.btn_enable =  Checkbutton(self.frm, variable = self.enable, command = self.btn_enable_cb)
        self.btn_enable.config(text = "Enable", font = ("Purisa", 16))
        self.btn_enable.grid(row = 0, column = 1)

    def init_temp(self):
        self.t = DoubleVar()
        self.temp = Label(self.frm, textvariable = self.t)
        self.temp.config(relief = FLAT, borderwidth = 5, font = ("Purisa", 50))
        self.temp.grid(row = 4, column = 0, columnspan = 1, rowspan = 5, stick = "w")

    def init_status(self):
        self.heat_status = StringVar()
        self.heat_status.set("heat off")
        self.lab_heat_status = Label(self.frm, textvariable = self.heat_status)
        self.lab_heat_status.config(relief = FLAT, borderwidth = 5, font = ("Purisa", 16))
        self.lab_heat_status.grid(row = 4, column = 1, columnspan = 1, rowspan = 1, stick = "we")
        self.lab_heat_status.config(background = "blue")

    def init_timer_display(self):
        self.time_left = StringVar()
        self.lab_seconds = Label(self.frm, textvariable = self.time_left)
        self.lab_seconds.config(relief = FLAT, borderwidth = 5, font = ("Purisa", 16))
        self.lab_seconds.grid(row = 5, column = 1, columnspan = 1, rowspan = 1, stick = "we")
 
    def init_control_btns(self):
        self.btn_var = IntVar()
        self.btn_tc =  Radiobutton(self.frm, variable = self.btn_var, value = Gui.BTN_TC, command = self.temp_btn_tc_cb)
        self.btn_tc.config(text = "Temp Control", indicatoron = 0, font = ("Purisa", 17))
        self.btn_tc.grid(row = 10, column = 0, sticky = "we", columnspan = 2)
        self.btn_pwm = Radiobutton(self.frm, variable = self.btn_var, value = Gui.BTN_PWM, command = self.temp_btn_pwm_cb)
        self.btn_pwm.config(text = "PWM", indicatoron = 0, font = ("Purisa", 17))
        self.btn_pwm.grid(row = 11, column = 0, sticky = "we", columnspan = 2)

        self.btn_tc_delay =  Radiobutton(self.frm, variable = self.btn_var, value = Gui.BTN_TC_LATER, command = self.temp_btn_tc_delay_cb)
        self.btn_tc_delay.config(text = "Temp Control Later", indicatoron = 0, font = ("Purisa", 17))
        self.btn_tc_delay.grid(row = 12, column = 0, sticky = "we", columnspan = 2)

        self.btn_pwm_delay = Radiobutton(self.frm, variable = self.btn_var, value = Gui.BTN_PWM_LATER, command = self.temp_btn_pwm_delay_cb)
        self.btn_pwm_delay.config(width = 25,text = "PWM Later ", indicatoron = 0, font = ("Purisa", 17))
        self.btn_pwm_delay.grid(row = 13, column = 0, sticky = "we", columnspan = 2)

        self.btn_off = Radiobutton(self.frm, variable = self.btn_var, value = Gui.BTN_OFF, command = self.temp_btn_off_cb)
        self.btn_off.config(width = 20,text = "Off", indicatoron = 0, font = ("Purisa", 17))
        self.btn_off.grid(row = 14, column = 0, sticky = "we", columnspan = 2, pady = (0,20)) 
        self.btn_list = [self.btn_off, self.btn_tc, self.btn_pwm, self.btn_tc_delay, self.btn_pwm_delay]
        
    def init_temp_inputs(self):
        self.temp_target = IntVar()
        self.pwm_target = IntVar()
        self.delay_time = IntVar()       
        self.temp_label_target = Label(self.frm, text = "Temp", font = ("Purisa", 15))
        self.temp_label_target.grid(row = 15, column = 0, sticky = "w")
        self.temp_input_target = Spinbox(self.frm, from_ = 0, to = 100, textvariable = self.temp_target, command = self.temp_input_target_cb)
        self.temp_input_target.config(width = 5, font = ("Purisa", 15))
        self.temp_input_target.grid(row = 15, column = 1, sticky = "we") 
        self.temp_label_pwm = Label(self.frm, text = "PWM", font = ("Purisa", 15))
        self.temp_label_pwm.grid(row = 16, column = 0, sticky = "w")
        self.temp_input_pwm = Spinbox(self.frm, from_ = 10, to = 100, textvariable = self.pwm_target, command = self.pwm_input_target_cb)
        self.temp_input_pwm.config(width = 5, font = ("Purisa", 15), values = (10,20,30,40,50,60,70,75,80,85,90,95,100))
        self.temp_input_pwm.grid(row = 16, column = 1, sticky = "we")
        self.label_delay_time = Label(self.frm, text = "Delay Timer", font = ("Purisa", 15))
        self.label_delay_time.grid(row = 17, column = 0, sticky = "w")
        self.input_delay_time = Spinbox(self.frm, from_ = 1, to = 24, textvariable = self.delay_time, command = self.input_delay_time_cb)
        self.input_delay_time.config(width = 5, font = ("Purisa", 15))
        self.input_delay_time.grid(row = 17, column = 1, sticky = "we")

    def set_tc_input_target(self, target):
        self.temp_target.set(target)

    def set_pwm_input_target(self, target):
        self.pwm_target.set(target)
        
    def set_input_delay_time(self, delay_time):
        self.delay_time.set(delay_time)
        
    def temp_btn_tc_cb(self):
        self.event_cb(Events.btn_tc)

    def temp_btn_tc_delay_cb(self): 
        self.event_cb(Events.btn_tc_delay)

    def temp_btn_pwm_cb(self):
        self.event_cb(Events.btn_pwm)

    def btn_enable_cb(self):
        if (self.enable.get() == 1):
            self.event_cb(Events.enable)
        else:
            self.event_cb(Events.disable)
        
    def temp_btn_pwm_delay_cb(self):
        self.event_cb(Events.btn_pwm_delay)
        
    def temp_btn_off_cb(self):
            self.event_cb(Events.btn_off)

    def temp_input_target_cb(self):
        self.event_cb(Events.set_tc, self.temp_target.get())

    def pwm_input_target_cb(self):
        self.event_cb(Events.set_pwm, float(self.pwm_target.get()) / 100)

    def input_delay_time_cb(self):
        self.event_cb(Events.set_pwm_delay_time, float(self.delay_time.get()))
        self.event_cb(Events.set_tc_delay_time, float(self.delay_time.get()))

    def read_temp(self):
        while(self.run):
            try:
                self.t.set(round(self.thermometer.read_temp(),1))
            except:
                return
            self.thermometer_sleep.sleep(1)

    def update_heat_status(self, heat_status):
        if (heat_status == 1):
            self.heat_status.set("heat on")
            self.lab_heat_status.config(background = "red")
        else:
            self.heat_status.set("heat off")
            self.lab_heat_status.config(background = "blue")

    def update_timer_display(self, seconds):
        s = time.strftime("%H:%M:%S", time.gmtime(seconds))
        self.time_left.set(s)

    def update_button(self, buttons, value, action):
        for btn_idx in buttons:
            if (action == self.ACTION_ENABLE):
                if (value):
                    self.btn_list[int(btn_idx)].config(state = NORMAL)
                else:
                    self.btn_list[int(btn_idx)].config(state = DISABLED)
            elif (action == self.ACTION_TEXT):
                self.btn_list[int(btn_idx)].config(text = value)
            elif (action == self.ACTION_SELECT):
                if (value == 1):
                    self.btn_list[int(btn_idx)].select()
                else:
                    self.btn_list[int(btn_idx)].deselect()


# Statemachine
class Statemachine():
    def __init__(self, start_state, next_cb):
        self._state = start_state
        self.next_cb = next_cb

    def next(self, next_state):
        self._state = next_state
        self.next_cb()

    def get_state(self):
        return self._state

    state = property(get_state, next)

class Event():
    def __init__(self, id, args):
        self.id = id
        self.args = args

# Brew controller incorpating temp control,
# pwm and delay timer
class BrewController():
    def __init__(self, **kwargs):
        # Init objects
        self.sm = Statemachine(ControlState.off, self.init_state)
        self.gui = Gui(kwargs['col_offset'], kwargs['name'], kwargs['device_id'] , self.queue_event)
        self.temp_controller = VariableTempControl(self.queue_event, self.queue_event, kwargs['device_id'], kwargs['pins'])
        self.pwm_controller = PwmControl(self.queue_event, self.queue_event, kwargs['pins'])
        self.pwm_delay_timer = Timer(self.queue_event, self.queue_event, self.gui.update_timer_display)
        self.tc_delay_timer = Timer(self.queue_event, self.queue_event, self.gui.update_timer_display)
        self.event_queue = Queue.Queue()

        # Init defaults
        self.default_tc_target = kwargs['tc_default']
        self.default_pwm_target = kwargs['pwm_default']
        self.default_delay_time = kwargs['delay_time_default']
        self.init_defaults()

        self.pwm_delay_time = self.default_delay_time
        self.tc_delay_time = self.default_delay_time

        # Init state
        self.sm.next(ControlState.disabled)

        # Start event thread
        self.run = 1
        self.th = Thread(target = self.process_queue)
        self.th.start()

    def queue_event(self, event, *args):
        self.event_queue.put(Event(event, args))

    def process_queue(self):
        while self.run:
            while not self.event_queue.empty():
                e = self.event_queue.get()
                self.process_event(e.id, e.args)
            time.sleep(0.25)

    def process_event(self, event, args):

        # setpoint set events get processed no matter what state we are in.
        # So do these first
        
        if (event == Events.set_tc):
           self.temp_controller.set_target(args[0])
           return
        elif (event == Events.set_pwm):
           self.pwm_controller.set_duty_cycle(args[0])
           self.temp_controller.set_duty_cycle(args[0])
           return
        elif (event == Events.set_pwm_delay_time):
           self.pwm_delay_time = args[0]
           return
        elif (event == Events.set_tc_delay_time):
           self.tc_delay_time = args[0]
           return

        # Heat status events get processed no matter what state
        # we are in
        if (event == Events.heat_on):
           self.gui.update_heat_status(1)
           return
        elif (event == Events.heat_off):
            self.gui.update_heat_status(0)
            return

        # Disable and shutdown works from any state
        if (event == Events.disable):
            self.sm.next(ControlState.disabled)
            return
        if (event == Events.shutdown):
            self.sm.next(ControlState.shutting_down)
            return

        # Process events that depend on state
        if (self.sm.state == ControlState.disabled):
            if (event == Events.enable):
                self.sm.next(ControlState.off)
                
        elif (self.sm.state == ControlState.off): 
            if (event == Events.btn_tc):  
                self.sm.next(ControlState.tc)
            elif (event == Events.btn_pwm):
                self.sm.next(ControlState.pwm)
            elif (event == Events.btn_pwm_delay):
                self.sm.next(ControlState.pwm_delayed)
            elif (event == Events.btn_tc_delay):
                self.sm.next(ControlState.tc_delayed)

        elif (self.sm.state == ControlState.tc):
            if (event == Events.btn_off):
                self.sm.next(ControlState.tc_stopping)

        if (self.sm.state == ControlState.tc_stopping):
            if (event == Events.controller_stopped):
                self.sm.next(ControlState.off)

        elif (self.sm.state == ControlState.tc_delayed):
            if (event == Events.btn_off):
                self.sm.next(ControlState.tc_delayed_stopping)
            elif (event == Events.timer_expired):
                self.sm.next(ControlState.tc)

        elif (self.sm.state == ControlState.tc_delayed_stopping):
            if (event == Events.timer_stopped):
                self.sm.next(ControlState.off)
                
        elif (self.sm.state == ControlState.pwm):
            if (event == Events.btn_off):
                self.sm.next(ControlState.pwm_stopping)

        elif (self.sm.state == ControlState.pwm_stopping):
            if (event == Events.controller_stopped):
                self.sm.next(ControlState.off)

        elif (self.sm.state == ControlState.pwm_delayed):
            if (event == Events.btn_off):
                self.sm.next(ControlState.pwm_delayed_stopping)
            elif (event == Events.timer_expired):
                self.sm.next(ControlState.pwm)

        elif (self.sm.state == ControlState.pwm_delayed_stopping):
            if (event == Events.timer_stopped):
                self.sm.next(ControlState.off)

        elif (self.sm.state == ControlState.shutting_down):
            if (event == Events.timer_stopped):
                self.sm.next(ControlState.off)


    def init_state(self):
        if (self.sm.state == ControlState.tc):
            self.temp_controller.start()
            self.gui.update_button(range(Gui.BTN_TC,Gui. BTN_PWM_LATER + 1), 0, Gui.ACTION_ENABLE)
            self.gui.update_button([Gui.BTN_TC], 1, Gui.ACTION_SELECT)
            
        elif (self.sm.state == ControlState.tc_stopping):
            self.temp_controller.stop()
            self.gui.update_button([Gui.BTN_TC], 0, Gui.ACTION_SELECT)

        elif (self.sm.state == ControlState.tc_delayed):
            self.tc_delay_timer.start(int(self.tc_delay_time) * 3600)
            self.gui.update_button(range(Gui.BTN_TC,Gui. BTN_PWM_LATER + 1), 0, Gui.ACTION_ENABLE)
            self.gui.update_button([Gui.BTN_TC_LATER], 1, Gui.ACTION_SELECT)

        elif (self.sm.state == ControlState.tc_delayed_stopping):
            self.tc_delay_timer.stop()
            self.gui.update_button([Gui.BTN_TC_DELAYED], 0, Gui.ACTION_SELECT)

        elif (self.sm.state == ControlState.pwm):
            self.pwm_controller.start()
            self.gui.update_button(range(Gui.BTN_TC,Gui. BTN_PWM_LATER + 1), 0, Gui.ACTION_ENABLE)
            self.gui.update_button([Gui.BTN_PWM], 1, Gui.ACTION_SELECT)

        elif (self.sm.state == ControlState.pwm_stopping):
            self.pwm_controller.stop()
            self.gui.update_button([Gui.BTN_PWM], 0, Gui.ACTION_SELECT)

        elif (self.sm.state == ControlState.pwm_delayed):
            self.pwm_delay_timer.start(int(self.pwm_delay_time)* 3600)
            self.gui.update_button(range(Gui.BTN_TC,Gui. BTN_PWM_LATER + 1), 0, Gui.ACTION_ENABLE)
            self.gui.update_button([Gui.BTN_PWM_LATER], 1, Gui.ACTION_SELECT)

        elif (self.sm.state == ControlState.pwm_delayed_stopping):
            self.pwm_delay_timer.stop()
            self.gui.update_button([Gui.BTN_PWM_LATER], 0, Gui.ACTION_SELECT)

        elif (self.sm.state == ControlState.off):
            self.gui.update_button([Gui.BTN_OFF], 1, Gui.ACTION_SELECT)
            self.gui.update_button(range(Gui.BTN_TC,Gui. BTN_PWM_LATER + 1), 1, Gui.ACTION_ENABLE)
            self.gui.update_timer_display(0)

        elif (self.sm.state == ControlState.disabled):
            self.gui.update_button(range(Gui.BTN_TC,Gui. BTN_PWM_LATER + 1), 0, Gui.ACTION_ENABLE)
            self.gui.update_button(range(Gui.BTN_TC,Gui. BTN_PWM_LATER + 1), 0, Gui.ACTION_SELECT)
            self.turn_off_everything()

        elif (self.sm.state == ControlState.shutting_down):
            self.run = 0
            self.turn_off_everything()
            self.gui.close()

    def turn_off_everything(self):
        self.temp_controller.stop()
        self.pwm_controller.stop()
        self.pwm_delay_timer.stop()
        self.tc_delay_timer.stop()
        
         
    def init_defaults(self):
        self.gui.set_tc_input_target(self.default_tc_target)
        self.gui.set_pwm_input_target(self.default_pwm_target)
        self.gui.set_input_delay_time(self.default_delay_time)
        self.pwm_controller.set_duty_cycle(float(self.default_pwm_target) / 100)
        self.temp_controller.set_target(int(self.default_tc_target))
        self.temp_controller.set_duty_cycle(float(self.default_pwm_target) / 100)



if __name__ == "__main__":

    def close():
        cntrs = [hlt, kettle, mt]
        
        # Check that we are ready to close
        for c in cntrs:
            if (c.sm.state != ControlState.off and c.sm.state != ControlState.disabled):
                return
        # We are ready to close
        for c in cntrs:
            c.queue_event(Events.shutdown)

        root.quit()

    # create logger
    logger = logging.getLogger('brew controller')
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler('debug.log')
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)


    def debug_log(message):
        "Automatically log the current function details."
        # Get the previous frame in the stack, otherwise it would
        # be this function!!!
        func = inspect.currentframe().f_back.f_code
        # Dump the message + the name of this function to the log.
        logger.debug("%s: %s in %s:%i" % (
            message, 
            func.co_name, 
            func.co_filename, 
            func.co_firstlineno
        ))

    root = Tk()
    root.protocol("WM_DELETE_WINDOW", close)
    hlt = BrewController(col_offset = 0, name = "HLT", device_id = "28-0000042dd80d", tc_default = "71", pwm_default = "50", delay_time_default = "12", pins = [3,4,5])
    kettle = BrewController(col_offset = 1, name = "Kettle", device_id = "28-0000042dd80d", tc_default = "95", pwm_default = "50", delay_time_default = "12", pins = [6,7,8])
    mt = BrewController(col_offset = 2, name = "Mash", device_id = "28-0000042dd80d", tc_default = "71", pwm_default = "50", delay_time_default = "12", pins = None)
    
    root.mainloop()
