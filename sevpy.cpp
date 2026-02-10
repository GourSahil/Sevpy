#include <iostream>
#include <filesystem>
#include <unordered_map>
#include <string>
#include <vector>

using namespace std;

string strip(const string& str){
    size_t start = str.find_first_not_of(" \t\n\r");
    size_t end = str.find_last_not_of(" \t\n\r");
    if (start == string::npos || end == string::npos) return ""; // String is all whitespace
    return str.substr(start, end - start + 1);
}

vector <string> split_string(const string& str, char delimiter){
    vector <string> result;
    string current;
    for (char c : str){
        if (c == delimiter){
            if (!current.empty()){
                result.push_back(strip(current));
                current.clear();
            }
        } else {
            current += c;
        }
    }
    if (!current.empty()){
        result.push_back(strip(current));
    }
    return result;
}

bool is_flag(const string& arg){
    return (arg.rfind("--", 0) == 0) || (arg.rfind("-", 0) == 0);
}

unordered_map<string, string> process_args(int argc, char* argv[], bool skip_first=false){
    unordered_map<string, string> flags;
    // basically if it is a value, then it is the value of the previous flag, otherwise it is a flag

    // Processes the cli arguments and only remembers flags as --flag or -f
    int alone_val_count = 0; // Counter for values that are not associated with any flag
    for (int i=0; i < argc; i++){
        if (skip_first && i == 0) continue; // skipping the first argument)
        // deciding to consider which thing as flag and as value
        if (is_flag(argv[i])){
            string flag_name = argv[i];
            string flag_value = ""; // Default value for flags without explicit value
            if (i + 1 < argc && !is_flag(argv[i + 1])){
                flag_value = argv[i + 1]; // Next argument is the value for this flag
                i++; // Skip the next argument since it's a value
            }
            flags[flag_name] = flag_value; // Store the flag and its value in the map
        }
        else {
            // This is a value without a preceding flag, we can choose to ignore it or handle it as needed
            flags[to_string(alone_val_count)] = argv[i]; // Storing it with its index as the key, or we could choose to ignore it
            alone_val_count++;
        }
    }
    return flags;
}

class SevPy {
    private:
        // Private members and methods can be defined here
        unordered_map<string, string> flags;

    public:
        // Public members and methods can be defined here

        void init(int argc, char* argv[]){
            // Implementation of the init method
            try{
                // Initialization code here
                cout << "Initializing SevPy..." << endl;
                this->flags = process_args(argc, argv, true); // Process the command line arguments and store the flags
            } catch (const exception& e){
                cout << "init() Failed!" << endl; // So that we know that the error is in the init function
                cleanup(e.what()); // Cleanup with error message if an exception occurs
            }
        }

        void run() {
            // Implementation of the run method
            cout << "Running SevPy..." << endl;
            try{
                // Running our code here
            } catch (const exception& e){
                cout << "run() Failed!" << endl; // So that we know that the error is in the run function
                cleanup(e.what()); // Cleanup with error message if an exception occurs
            }
        }

        void cleanup(string error_message="") {
            // Implementation of the cleanup method
            if (!error_message.empty()) {
                cerr << "Error during execution: " << error_message << endl;
            }
            cout << "Cleaning up SevPy..." << endl;
        }
};

int main(int argc, char* argv[]){
    // Entry point of the program
    try {
        SevPy sevpy;
        sevpy.init(argc, argv);
        sevpy.run();
        sevpy.cleanup();
    } catch (const exception& e){
        cerr << "An unexpected error occurred: " << e.what() << endl;
        return 1; // Return a non-zero value to indicate an error
    }
}