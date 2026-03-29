from ingest import btc_api_pipeline
import threading 
import os


#hard stop timer for development purposes, ultimately dont want a kill switch related to time 
def hard_stop_after(seconds: int):
    """
    schedule a hard stop that terminates the process after a duration

    Args:
        seconds (int): number of seconds before termination

    Returns:
        None 
    """
    def _kill():
        """
        force exit the process immediately

        Args:
            None

        Returns:
            None 
        """
        print("⏰ 4 hours reached — force exiting process")
        os._exit(0)   # hard kill: stops all threads immediately

    timer = threading.Timer(seconds, _kill)
    timer.daemon = True
    timer.start()

def main():
    #test run 1, stop after 4 hours
    hard_stop_after(4 * 60 * 60) 
    
    btc_api_pipeline()

if __name__ == "__main__":
    main()
    
