from naoqi import *
import time 
import datetime
import numpy as np
import threading

import tensorflow as tf

import Queue

from face_module import get_face
from neural_net import *

import itertools
import fasteners


epsilon = 0.1
mu = 0.9
epoch = 10

TIME_SIG = 4#four-four
MEASURES = 8
TRIAL_NUM = MEASURES
BPM = 60

HOST = "127.0.0.1"
PORT= 40835

ANGLE_DIM= 2
FACE_DIM= 1
LEARN_NUM = 2

ACT_GEN_WIDTH = 4

LOOP = TIME_SIG *2
INPUT_DIM = ANGLE_DIM * LOOP
OUTPUT_DIM = FACE_DIM

#time of start learning
ML_TIME = LOOP*2

def conv_angle(key_str,angle):
    key_list = ["HeadYaw","HeadPitch","LShoulderRoll", "RShoulderRoll","LShoulderPitch", "RShoulderPitch","LElbowRoll", "RElbowRoll","LElbowYaw", "RElbowYaw"]
    angle_array = np.array([[-2.0,2.0],[-0.6,0.5],[-0.3,1.3],[-1.3,0.3],[-2.0,2.0],[-2.0,2.0],[-1.5,0],[0,1.5],[-2.0,2.0],[-2.0,2.0]])
    index=key_list.index(key_str)
    a = abs(angle_array[index,0])+abs(angle_array[index,1])
    b = angle_array[index,0]
    return angle*a + b


def nao_move(proxy,angle,t):
    speed = 1.0
    print("move")
    #motion_proc.changeAngles(["HeadYaw", "HeadPitch"], [conv_angle("HeadYaw",angle[0,0]), conv_angle("HeadPitch",angle[0,1])], speed)
    proxy.changeAngles(["LShoulderRoll", "RShoulderRoll"], [conv_angle("LShoulderRoll",angle[0,0]), conv_angle("RShoulderRoll",angle[0,1])],speed )
    #motion_proc.changeAngles(["LShoulderPitch", "RShoulderPitch"], [conv_angle("LShoulderPitch",angle[0,0]), conv_angle("RShoulderPitch",angle[0,1])],speed)
    #motion_proc.changeAngles(["LElbowRoll", "RElbowRoll"], [conv_angle("LElbowRoll",angle[0,0]), conv_angle("RElbowRoll",angle[0,1])],speed)
    #motion_proc.changeAngles(["LElbowYaw", "RElbowYaw"], [conv_angle("LElbowYaw",angle[0,0]), conv_angle("RElbowYaw",angle[0,1])],speed)

class Motion:
  _lock = threading.Lock()
  #_lock = fasteners.InterProcessLock('/var/tmp/lockfile')
  def __init__(self,robot_name,robot,robot_move_func):
    self.robot= robot
    self.robot_move_func= robot_move_func

    self.neural = Neural(robot_name,INPUT_DIM,OUTPUT_DIM,LEARN_NUM)
    self._neural = Neural(robot_name+"o",INPUT_DIM,OUTPUT_DIM,LEARN_NUM)
    self.neural.get_model("new")
    self._neural.get_model("new")

    self.face_history = np.zeros((100,FACE_DIM))
    self.angle_history = np.zeros((100,ANGLE_DIM))

    self.count = 0
    self.graph = tf.get_default_graph()

    self.index = 0

  def run(self):

    th_robot = threading.Thread(target=self.motion_loop,args=())
    th_learning = threading.Thread(target=self.ml_loop,args=())

    th_learning.setDaemon(True)

    th_robot.start()
    th_learning.start()

    th_robot.join()
    #th_learning.join()

  #def ml_loop(self,present_angle,angle,face):
  def ml_loop(self):
    mark=0
    with self.graph.as_default():
      if(self.count<ML_TIME):
        mode="new"
      else:
        mode="present"
      while(True):
        if(self.count%int(ML_TIME)==0):
          if(mark==0):
            input_array = np.reshape(np.hstack((self.angle_history[-LOOP:,:])),(-1,INPUT_DIM))
            output_array = np.reshape(np.hstack((self.face_history[-1,:])),(-1,OUTPUT_DIM))
            print("before learning",mode,mark)
            #self._neural.train(np.reshape(input_array,(-1,INPUT_DIM)),np.reshape(output_array,(-1,OUTPUT_DIM)),mode,self.count)  
            Motion._lock.acquire()
            self.neural.model.compile(optimizer="adam",
              loss="mean_squared_error",
              metrics=["accuracy"])
            self.neural.model.fit(x=input_array, y=output_array, nb_epoch=2)
            Motion._lock.release()
            mark=1
        else:
          mark = 0
        #self.neural.train(np.reshape(np.hstack((present_angle,angle)),(-1,ANGLE_DIM*2)),np.reshape(face,(-1,FACE_DIM)))  

  def get_motion_para(self,i):
    t= np.random.rand()
    t = 60.0/float(BPM)
    print("t",t)

    if(i<TIME_SIG):
      angle= np.random.rand(ANGLE_DIM,TIME_SIG)
      print("random angle",angle)
    else:

      split_size = int(ACT_GEN_WIDTH)
      N=ANGLE_DIM*TIME_SIG#dim of estimation
      candidate_score = np.zeros(split_size**N)

      with self.graph.as_default():

        candidate_array = self.set_candidate_array(1)
        reshape=np.reshape(candidate_array,[-1,INPUT_DIM])
        tic = time.clock()
        Motion._lock.acquire()
        candidate_score = self.neural.predict(reshape)
        Motion._lock.release()
        toc = time.clock()
        print("time {0:0.4f} seconds".format(toc-tic))

        angle = candidate_array[np.argmax(candidate_score),-ANGLE_DIM*TIME_SIG:]
        #angle= np.random.rand(ANGLE_DIM,TIME_SIG)

      print("predicted angle",angle)
    return t,np.reshape(angle,(-1,ANGLE_DIM))

  def ml_loop(self):
    mark=0
    with self.graph.as_default():
      if(self.count<ML_TIME):
        mode="new"
      else:
        mode="present"
      while(True):
        if(self.count%int(ML_TIME)==0):
          if(mark==0):
            input_array = np.reshape(np.hstack((self.angle_history[-LOOP:,:])),(-1,INPUT_DIM))
            output_array = np.reshape(np.hstack((self.face_history[-1,:])),(-1,OUTPUT_DIM))
            print("before learning",mode,mark)
            #self._neural.train(np.reshape(input_array,(-1,INPUT_DIM)),np.reshape(output_array,(-1,OUTPUT_DIM)),mode,self.count)  
            Motion._lock.acquire()
            self.neural.model.compile(optimizer="adam",
              loss="mean_squared_error",
              metrics=["accuracy"])
            self.neural.model.fit(x=input_array, y=output_array, nb_epoch=2)
            Motion._lock.release()
            mark=1
        else:
          mark = 0
        #self.neural.train(np.reshape(np.hstack((present_angle,angle)),(-1,ANGLE_DIM*2)),np.reshape(face,(-1,FACE_DIM)))  

  def set_candidate_array(self,t):

    split_size = int(ACT_GEN_WIDTH)
    N=ANGLE_DIM*TIME_SIG#dim of estimation
    l=np.linspace(0,1,split_size)
    candidate_array = np.zeros((split_size**N,INPUT_DIM))

    if(t==0):

      index = 0

      for v in itertools.product(l,repeat=N):
        candidate_array[index,:] = np.hstack((np.zeros(N),np.array(v)))
        index+=1

      self.index = index

    else:
      candidate_array[:,:N] = np.tile(np.hstack((self.angle_history[-TIME_SIG:,:])),(self.index,1))

    return candidate_array

  def robot_move(self,angle):
    face_file = "/home/kazumi/prog/emopy_test/test_face.csv"
    for t in range(TIME_SIG):
      self.robot_move_func(self.robot,np.reshape(angle[t,:],(-1,ANGLE_DIM)),t)

      #face2##
      if(os.path.exists(face_file)==True):
        if(os.stat(face_file).st_size!=0):
          face = np.loadtxt(face_file,delimiter=",")
          #print("face",face[-1,:3],face.shape)
          #if(face.shape>500):
          #  os.remove(face_file)
          #  print("delete")

          self.face_history[:-1,:] = self.face_history[1:,:]
          self.angle_history[:-1,:] = self.angle_history[1:,:]

          self.face_history[-1,:] = face[-1,2]
          self.angle_history[-1,:] = angle[t,:]

      else:
        print("no face")

        #learning(neural,present_angle,angle[0,:],face)
        #with open("learning.txt",'a') as f:
        #  f.write(str(present_angle)+str(angle[0,:])+","+str(face)+"\n")

      #present_angle = np.reshape(angle,(ANGLE_DIM))

      time.sleep(1.0)



  def motion_loop(self):
    present_angle = np.zeros(ANGLE_DIM)
    self.robot_move_func(self.robot,np.reshape(present_angle,(-1,ANGLE_DIM)),1)

    candidate_array = self.set_candidate_array(0)
    self.count = 0
    t,angle = self.get_motion_para(0)
    print("angle",angle)

    for i in range(MEASURES):
      self.count = i
      print("count",self.count)

      mov_thr = threading.Thread(target=self.robot_move,args=(angle,))
      mov_thr.start()

      t,angle = self.get_motion_para(i+1)
      mov_thr.join()

def main():
  
  robot_name = "NAO"
  robot = ALProxy("ALMotion", HOST, PORT)
  robot_move_func = nao_move
  motion_main=Motion(robot_name,robot,robot_move_func)
  motion_main.run()

if __name__ == '__main__':
  main()

  #q_face= Queue.Queue()
  #th_face = threading.Thread(target=get_face,args=(q_face,))

  #th_face.setDaemon(True)
