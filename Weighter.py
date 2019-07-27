'''
Created on 26 Feb 2017

@author: jkiesele
'''

from __future__ import print_function
import numpy as np

import matplotlib
#if no X11 use below
matplotlib.use('Agg')

class Weighter(object):
    '''
    contains the histograms/input to calculate jet-wise weights
    '''
    def __init__(self):

        self.Axixandlabel=[]
        self.axisX=[]
        self.axisY=[]
        self.hists =[]
        self.removeProbabilties=[]
        self.binweights=[]
        self.distributions=[]
        self.xedges=[np.array([])]
        self.yedges=[np.array([])]
        self.classes=[]
        self.refclassidx=0
        self.undefTruth=[]
    	self.ignore_when_weighting=[]
        self.removeUnderOverflow=False
        
    def __eq__(self, other):
        'A == B'
        def _all(x):
            if hasattr(x, 'all'):
                return x.all()
            if hasattr(x, '__iter__'):
                return all(x)
            else: return x
            
        def comparator(this, that):
            'compares lists of np arrays'
            return _all((i == j).all() for i,j in zip(this, that))
        
        #empty
        if len(self.Axixandlabel) == len(other.Axixandlabel) and len(self.Axixandlabel) == 0:
            return True
        
        return self.Axixandlabel == other.Axixandlabel and \
           _all(self.axisX == other.axisX) and \
           _all(self.axisY == other.axisY) and \
           comparator(self.hists, other.hists) and \
           comparator(self.removeProbabilties, other.removeProbabilties) and \
           self.classes == other.classes and \
           self.refclassidx == other.refclassidx and \
           self.undefTruth == other.undefTruth and \
           comparator(self.binweights, other.binweights) and \
           comparator(self.distributions, other.distributions) and \
           _all(self.xedges == other.xedges) and \
           _all(self.yedges == other.yedges)
    
    def __ne__(self, other):
        'A != B'
        return not (self == other)
        
    def setBinningAndClasses(self,bins,nameX,nameY,classes):
        self.axisX= bins[0]
        self.axisY= bins[1]
        self.nameX=nameX
        self.nameY=nameY
        self.classes=classes
        if len(self.classes)<1:
            self.classes=['']
        
    def addDistributions(self,Tuple, referenceclass="flatten"):
        selidxs=[]
        
        ytuple=Tuple[self.nameY]
        xtuple=Tuple[self.nameX]
        
        useonlyoneclass=len(self.classes)==1 and len(self.classes[0])==0
        
        if not useonlyoneclass:
            labeltuple=Tuple[self.classes]
            for c in self.classes:
                selidxs.append(labeltuple[c]>0)
        else:
            selidxs=[np.zeros(len(xtuple),dtype='int')<1]
            
        
        for i in range(len(self.classes)):
            if not referenceclass=="lowest": 
                tmphist,xe,ye=np.histogram2d(xtuple[selidxs[i]],ytuple[selidxs[i]],[self.axisX,self.axisY],normed=True)
            else:
                tmphist,xe,ye=numpy.histogram2d(xtuple[selidxs[i]],ytuple[selidxs[i]],[self.axisX,self.axisY])
            #print(self.classes[i], xtuple[selidxs[i]], len(xtuple[selidxs[i]]))
            self.xedges=xe
            self.yedges=ye
            if len(self.distributions)==len(self.classes):
                self.distributions[i]=self.distributions[i]+tmphist
            else:
                self.distributions.append(tmphist)
            
    def printHistos(self,outdir):
        def plotHist(hist,outname):
            import matplotlib.pyplot as plt
            H=hist.T
            fig = plt.figure()
            ax = fig.add_subplot(111)
            X, Y = np.meshgrid(self.xedges, self.yedges)
            ax.pcolormesh(X, Y, H)
            if self.axisX[0]>0:
                ax.set_xscale("log", nonposx='clip')
            else:
                ax.set_xlim([self.axisX[1],self.axisX[-1]])
                ax.set_xscale("log", nonposx='mask')
            #plt.colorbar()
            fig.savefig(outname)
            plt.close()
            
        for i in range(len(self.classes)):
            if len(self.distributions):
                plotHist(self.distributions[i],outdir+"/dist_"+self.classes[i]+".pdf")
                plotHist(self.removeProbabilties[i] ,outdir+"/remprob_"+self.classes[i]+".pdf")
                plotHist(self.binweights[i],outdir+"/weights_"+self.classes[i]+".pdf")
                reshaped=self.distributions[i]*self.binweights[i]
                plotHist(reshaped,outdir+"/reshaped_"+self.classes[i]+".pdf")
            
        
    def createRemoveProbabilitiesAndWeights(self,referenceclass='isB'):
        referenceidx=-1
        if referenceclass not in ['flatten', 'lowest']:
            try:
                referenceidx=self.classes.index(referenceclass)
            except:
                print('createRemoveProbabilities: reference index not found in class list')
                raise Exception('createRemoveProbabilities: reference index not found in class list')
            
        if len(self.classes) > 0 and len(self.classes[0]):
            self.Axixandlabel = [self.nameX, self.nameY]+ self.classes
        else:
            self.Axixandlabel = [self.nameX, self.nameY]
        
        self.refclassidx=referenceidx
        
        refhist=np.zeros((len(self.axisX)-1,len(self.axisY)-1), dtype='float32')
        refhist += 1
        
        if referenceidx >= 0:
            refhist=self.distributions[referenceidx]
            refhist=refhist/np.amax(refhist)
        
    
        def divideHistos(a,b):
            out=np.array(a)
            for i in range(a.shape[0]):
                for j in range(a.shape[1]):
                    if b[i][j]:
                        out[i][j]=a[i][j]/b[i][j]
                    else:
                        out[i][j]=-10
            return out
                
        probhists=[]
        weighthists=[]
        
        bin_counts = []
        for i in range(len(self.classes)):
            if self.classes[i] in self.ignore_when_weighting:  continue
            bin_counts.append(self.distributions[i])
        bin_min = np.array(np.minimum.reduce(bin_counts))
        for i in range(len(self.classes)):
            tmphist=self.distributions[i]
            if referenceclass=="lowest": 
                ratio=divideHistos(bin_min,tmphist)
            else:
            	if np.amax(tmphist):
                	tmphist=tmphist/np.amax(tmphist)
                else:
                	print('Warning: class '+self.classes[i]+' empty.')
                ratio=divideHistos(refhist,tmphist)
                ratio=ratio/np.amax(ratio)#norm to 1

            ratio[ratio<0]=1
            ratio[ratio==np.nan]=1
            weighthists.append(ratio)
            probhists.append(1-ratio)
        print ("Weights:")
        np.set_printoptions(precision=3, suppress=True)
        print(["Min evts per bin"] + self.classes)
        print(np.column_stack(tuple([bin_min] + weighthists))) 
        self.removeProbabilties=probhists
        self.binweights=weighthists
        
        #make it an average 1
        #for i in range(len(self.binweights)):
        #    self.binweights[i]=self.binweights[i]/np.average(self.binweights[i])
    
    
        
        
    def createNotRemoveIndices(self,Tuple):
        if len(self.removeProbabilties) <1:
            print('removeProbabilties bins not initialised. Cannot create indices per jet')
            raise Exception('removeProbabilties bins not initialised. Cannot create indices per jet')
        
        tuplelength=len(Tuple)
        
        notremove=np.zeros(tuplelength)
        counter=0
        xaverage=[]
        norm=[]
        yaverage=[]
        count_out, count_rem = 0, 0
        
        useonlyoneclass=len(self.classes)==1 and len(self.classes[0])==0
        
        for c in self.classes:
            xaverage.append(0)
            norm.append(0)
            yaverage.append(0)
            
        
        incomplete_class_phasespace = False
        for jet in iter(Tuple[self.Axixandlabel]):
            binX =  self.getBin(jet[self.nameX], self.axisX)
            binY =  self.getBin(jet[self.nameY], self.axisY)
            out, rem = False, False
            for index, classs in enumerate(self.classes):
                if  useonlyoneclass or 1 == jet[classs]:
                    rand=np.random.ranf()
                    prob = self.removeProbabilties[index][binX][binY]
                    
                    if self.removeUnderOverflow and (jet[self.nameX] < self.axisX[0] or jet[self.nameY] < self.axisY[0] or jet[self.nameX] > self.axisX[-1] or jet[self.nameY] > self.axisY[-1]):
                        #print("over/underflow")
                        out = True
                        notremove[counter]=0
                    elif rand < prob and index != self.refclassidx:
                        notremove[counter]=0
                        rem = True
                    else:
                        #print('keep',index,self.refclassidx,jet[classs],classs)
                        notremove[counter]=1
                        xaverage[index]+=jet[self.nameX]
                        yaverage[index]+=jet[self.nameY]
                        norm[index]+=1
            
                    counter += 1
                elif sum([jet[classs] for classs in self.classes])==0:
                    notremove[counter]=0
                    counter +=1
                    incomplete_class_phasespace = True
            if out: count_out +=1
            if rem: count_rem +=1
        print('Under/Overflow:  {} % , Randomly removed: {} %'.format(round(count_out/float(counter)*100), round(count_rem/float(counter)*100)) )
        
        if incomplete_class_phasespace:
            print("WARNING: Defined truth classes don't sum up to 1 in probability")
        if not len(notremove) == counter:
            raise Exception("tuple length must match remove indices length. Probably a problem with the definition of truth classes in the ntuple and the TrainData class")
        
        return notremove

    
        
    def getJetWeights(self,Tuple):
        if len(self.binweights) <1:
            raise Exception('weight bins not initialised. Cannot create weights per jet')
        
        weight = np.zeros(len(Tuple))
        jetcount=0
        
        useonlyoneclass=len(self.classes)==1 and len(self.classes[0])==0
        count_out = 0
        count_undef = 0
        
        for jet in iter(Tuple[self.Axixandlabel]):
            binX =  self.getBin(jet[self.nameX], self.axisX)
            binY =  self.getBin(jet[self.nameY], self.axisY)
            out=False
            for index, classs in enumerate(self.classes):
                if 1 == jet[classs] or useonlyoneclass:
                    jet_out_of_range = (jet[self.nameX] < self.axisX[0] or jet[self.nameY] < self.axisY[0] or jet[self.nameX] > self.axisX[-1] or jet[self.nameY] > self.axisY[-1])
                    #if self.removeUnderOverflow and (jet[self.nameX] < self.axisX[0] or jet[self.nameY] < self.axisY[0] or jet[self.nameX] > self.axisX[-1] or jet[self.nameY] > self.axisY[-1]):
                    if self.removeUnderOverflow and jet_out_of_range:
                    	weight[jetcount]=0
                        out = True
                    else:
                        weight[jetcount]=(self.binweights[index][binX][binY])
                #else: 
                #    	weight[jetcount]=0
                    
            if sum([jet[classs] for classs in self.classes])==0:
                incomplete_class_phasespace = True
                count_undef += 1
            if out: count_out +=1
            jetcount=jetcount+1        

        if self.removeUnderOverflow: print('Under/Overflow:  {} % '.format(round(count_out/float(jetcount)*100,2)))
        if count_undef > 0: 
            print("WARNING: Defined truth classes don't sum up to 1 in probability")
            print('Undefined:  {} % '.format(round(count_undef/float(jetcount)*100,2)))

            print('Weight average: ',weight.mean())
            print('Weight average (non-zero-only): ',weight[weight > 0].mean())
            print('Fraction of 0 weights: ', len(weight[weight == 0])/float(len(weight)))
        
        return weight
        
        
    def getBin(self,value, bins):
        """
        Get the bin of "values" in axis "bins".
        Not forgetting that we have more bin-boundaries than bins (+1) :)
        """
        for index, bin in enumerate (bins):
            # assumes bins in increasing order
            if value < bin:
                return index-1            
        #print (' overflow ! ', value , ' out of range ' , bins)
        return bins.size-2

        
        
